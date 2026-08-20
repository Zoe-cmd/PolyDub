"""Pipeline 编排：阶段独立可跑、中间结果落盘、支持断点续跑。

流程（多说话人 + 重叠分离）：
extract → separate(人声/背景) → diarize(谁在何时说话，含重叠)
→ transcribe(逐说话人转写 + 重叠语音分离) → translate → tts → align → mix → mux
"""
import json
import os
from pathlib import Path

from ..utils.logging import get_logger
from ..utils.workspace import Workspace
from ..utils import subtitles
from ..utils.audio import cut
from ..video import extractor
from ..video.muxer import mux as mux_video
from ..asr.transcriber import Transcriber
from ..diarization.speaker_diarization import Diarizer
from ..separation.vocal_separator import VocalSeparator
from ..translation.translator import Translator
from ..tts.synthesizer import Synthesizer
from ..alignment import aligner
from ..mixing import audio_mixer
from ..speakers import SpeakerManager

log = get_logger(__name__)

_STAGE_ORDER = ["extract", "separate", "diarize", "transcribe", "translate", "tts", "align", "mix", "mux"]


class Pipeline:
    def __init__(self, config, input_path, source_lang=None, target_lang=None, output=None):
        self.config = config or {}
        self.input_path = input_path
        self.source_lang = source_lang
        self.target_lang = target_lang or "zh"
        self.output = output
        self.ws = Workspace(input_path, root=self.config.get("workspace", {}).get("root", "outputs"))
        self.speakers = SpeakerManager(self.config.get("speakers", {}).get("mapping_file"))
        from ..utils import gpu

        # 禁用 cuDNN + speechbrain 懒加载补丁，规避与 faster-whisper 的同进程 CUDA 冲突
        gpu.configure_torch()

    # ---- IO helpers ----
    def _load_json(self, name):
        p = self.ws.path(name)
        if not p.exists():
            raise RuntimeError(f"[Pipeline] 缺少 {name} — 请先运行前一阶段")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_json(self, name, obj):
        subtitles.write_json(obj, self.ws.path(name))

    def _get_utterances(self):
        p = self.ws.path("utterances.json")
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        raise RuntimeError("[Pipeline] 请先运行 --stage transcribe")

    # ---- 音频提取 ----
    def stage_extract(self):
        out = self.ws.path("audio.wav")
        out_hq = self.ws.path("audio_hq.wav")
        if out.exists():
            log.info("[Video] audio.wav exists, skip")
        else:
            extractor.extract_audio(self.input_path, out, sample_rate=16000, channels=1)
        if out_hq.exists():
            log.info("[Video] audio_hq.wav exists, skip")
        else:
            extractor.extract_audio_hq(self.input_path, out_hq, sample_rate=44100, channels=2)
        return out

    # ---- 人声/背景分离 ----
    def stage_separate(self):
        self.stage_extract()
        vocals = self.ws.path("vocals.wav")
        background = self.ws.path("background.wav")
        if vocals.exists() and background.exists():
            log.info("[Separation] vocals/background exist, skip")
            return {"vocals": str(vocals), "background": str(background)}
        cfg = self.config.get("separation", {})
        v = VocalSeparator(model=cfg.get("vocal_model", "htdemucs"), device=cfg.get("device", "cuda"))
        try:
            return v.separate(self.ws.path("audio_hq.wav"), vocals, background)
        finally:
            v.close()

    # ---- 说话人分离（含重叠信息）----
    def stage_diarize(self):
        self.stage_extract()
        if self.ws.exists("diarization.json"):
            d = self._load_json("diarization.json")
            turns, speakers = d["turns"], d["speakers"]
            log.info("[Diarization] diarization.json exists, skip model")
        else:
            cfg = self.config.get("diarization", {})
            token = os.environ.get(cfg.get("hf_token_env", "HF_TOKEN")) or cfg.get("hf_token")
            d_obj = Diarizer(
                backend=cfg.get("backend", "pyannote"),
                model=cfg.get("model", "pyannote/speaker-diarization-3.1"),
                hf_token=token,
                device=cfg.get("device", "cuda"),
                threshold=cfg.get("threshold"),
            )
            try:
                turns, speakers = d_obj.diarize(
                    self.ws.path("audio.wav"),
                    num_speakers=cfg.get("num_speakers"),
                    min_speakers=cfg.get("min_speakers"),
                    max_speakers=cfg.get("max_speakers"),
                )
                self._save_json("diarization.json", {"turns": turns, "speakers": speakers})
            finally:
                d_obj.close()

        self.speakers.ensure_roles(speakers)
        return {"turns": turns, "speakers": speakers}

    # ---- 逐说话人转写（含重叠分离）----
    def stage_transcribe(self):
        if self.ws.exists("utterances.json"):
            log.info("[ASR] utterances.json exists, skip")
            return self._load_json("utterances.json")
        self.stage_separate()
        self.stage_diarize()

        from .utterances import build_utterances, build_clusters, SpeakerEmbedding
        from ..separation.speech_separator import SpeechSeparator

        asr_cfg = self.config.get("asr", {})
        lang = asr_cfg.get("language") or self.source_lang or None
        t = Transcriber(
            model_size=asr_cfg.get("model", "Systran/faster-whisper-large-v3"),
            device=asr_cfg.get("device", "cuda"),
            compute_type=asr_cfg.get("compute_type", "float16"),
            language=lang,
            beam_size=int(asr_cfg.get("beam_size", 5)),
            vad_filter=bool(asr_cfg.get("vad_filter", False)),
        )

        turns = self._load_json("diarization.json")["turns"]
        vocals = self.ws.path("vocals.wav")
        if not vocals.exists():
            vocals = self.ws.path("audio_hq.wav")

        speakers = sorted({turn["speaker"] for turn in turns})
        refs = self._extract_references(speakers, turns, vocals)

        # 按最大重叠人数加载对应的分离模型（2 人用 2mix，3 人用 3mix）
        clusters = build_clusters(turns)
        max_spk = max((len(cl) for cl in clusters), default=1)
        sep_cfg = self.config.get("separation", {})
        separators = {}
        embedding = None
        if max_spk >= 2:
            separators[2] = SpeechSeparator(
                model=sep_cfg.get("speech_model", "speechbrain/sepformer-libri2mix"),
                device=sep_cfg.get("device", "cuda"),
            )
        if max_spk >= 3:
            separators[3] = SpeechSeparator(
                model=sep_cfg.get("speech_model_3spk", "speechbrain/sepformer-libri3mix"),
                device=sep_cfg.get("device", "cuda"),
            )
        if separators:
            log.info("[ASR] 检测到重叠说话区域（最大 %d 人同时说话），加载分离模型", max_spk)
            embedding = SpeakerEmbedding(device=sep_cfg.get("device", "cuda"))

        try:
            workdir = self.ws.path("chunks")
            utterances, _ov = build_utterances(vocals, turns, t, separators, embedding, workdir, refs)
            if not lang:
                lang = self._detect_language(t, vocals)
            payload = {"meta": {"language": lang}, "utterances": utterances}
            self._save_json("utterances.json", payload)
            subtitles.write_srt(utterances, self.ws.path("subtitles.srt"))
            subtitles.write_ass(utterances, self.ws.path("subtitles.ass"))
            log.info("[ASR] wrote utterances.json / subtitles.srt / subtitles.ass")
            return payload
        finally:
            t.close()
            for s in separators.values():
                s.close()
            if embedding is not None:
                embedding.close()

    def _detect_language(self, transcriber, vocals, max_sec=15.0):
        probe = self.ws.path("chunks", "_probe.wav")
        cut(vocals, 0, max_sec, probe)
        _segments, meta = transcriber.transcribe(probe)
        return meta.get("language")

    # ---- 翻译 ----
    def stage_translate(self):
        if self.ws.exists("translation.json"):
            log.info("[Translation] translation.json exists, skip")
            return self._load_json("translation.json")["utterances"]
        data = self._get_utterances()
        source = self.source_lang or data.get("meta", {}).get("language")
        if not source:
            raise RuntimeError("[Translation] 未知源语言，请传 --source-lang")
        utterances = data["utterances"]

        tr = Translator(self.config)
        try:
            utterances = tr.translate(utterances, source, self.target_lang)
            self._save_json(
                "translation.json",
                {"source": source, "target": self.target_lang, "utterances": utterances},
            )
            trans_segs = [{**s, "text": s.get("translated_text", s["text"])} for s in utterances]
            subtitles.write_srt(trans_segs, self.ws.path("subtitles_translated.srt"))
            subtitles.write_ass(trans_segs, self.ws.path("subtitles_translated.ass"))
            log.info("[Translation] wrote translation.json / subtitles_translated.srt / .ass")
            return utterances
        finally:
            tr.close()

    # ---- TTS 配音 ----
    def stage_tts(self):
        if self.ws.exists("tts_map.json"):
            log.info("[TTS] tts_map.json exists, skip")
            return self._load_json("tts_map.json")["audio"]
        translation = self._load_json("translation.json")
        utterances = translation["utterances"]
        turns = self._load_json("diarization.json")["turns"]
        vocals = self.ws.path("vocals.wav")
        if not vocals.exists():
            vocals = self.ws.path("audio_hq.wav")

        speakers = sorted({s.get("speaker", "SPEAKER_00") for s in utterances})
        refs = self._extract_references(speakers, turns, vocals)

        synth = Synthesizer(self.config)
        tts_dir = self.ws.path("tts")
        tts_dir.mkdir(parents=True, exist_ok=True)

        from ..utils.env import read_env

        env = read_env()
        tts_engine = (env.get("TTS_ENGINE") or "").strip().lower()
        items = []
        if tts_engine == "edge":
            from ..tts.edge_synthesizer import assign_edge_voices

            voices = assign_edge_voices(utterances, refs, self.target_lang)
            for i, seg in enumerate(utterances):
                out = tts_dir / f"seg_{i:04d}.wav"
                if out.exists():
                    continue
                spk = seg.get("speaker", "SPEAKER_00")
                items.append(
                    {"text": seg["translated_text"], "lang": self.target_lang,
                     "voice": voices.get(spk), "out": str(out)}
                )
        else:
            for i, seg in enumerate(utterances):
                out = tts_dir / f"seg_{i:04d}.wav"
                if out.exists():
                    continue
                spk = seg.get("speaker", "SPEAKER_00")
                ref = refs.get(spk)
                if not ref:
                    raise RuntimeError(f"[TTS] 说话人 {spk} 无参考音频（diarization 未覆盖？）")
                items.append(
                    {"ref": ref, "text": seg["translated_text"], "lang": self.target_lang,
                     "out": str(out), "df": 1.0}
                )

        if items:
            synth.synth_batch(items)
            # 短句对齐收紧：配音明显长于原时间槽时，用 duration_factor 加速重新合成
            if tts_engine != "edge":
                self._retry_long_duration(synth, tts_dir, utterances, refs)
        else:
            log.info("[TTS] 全部 %d 段已合成，跳过", len(utterances))

        audio = [str(tts_dir / f"seg_{i:04d}.wav") for i in range(len(utterances))]
        self._save_json("tts_map.json", {"audio": audio})
        log.info("[TTS] wrote tts_map.json (%d segments)", len(audio))
        return audio

    def _extract_references(self, speakers, turns, vocals_path):
        refs = {}
        for spk in speakers:
            cands = [t for t in turns if t["speaker"] == spk]
            if not cands:
                continue
            best = max(cands, key=lambda t: t["end"] - t["start"])
            start = best["start"]
            end = min(best["end"], start + 10.0)
            out = self.ws.path("tts", f"ref_{spk}.wav")
            if not out.exists():
                cut(vocals_path, start, end, out)
            refs[spk] = str(out)
        return refs

    def _retry_long_duration(self, synth, tts_dir, utterances, refs):
        """对时长明显超过原时间槽的配音，用 IndexTTS duration_factor(<1) 加速重合成。"""
        from ..utils.audio import duration as _dur

        retry = []
        for i, seg in enumerate(utterances):
            out = tts_dir / f"seg_{i:04d}.wav"
            if not out.exists():
                continue
            slot = seg["end"] - seg["start"]
            if slot <= 0:
                continue
            dur = _dur(out)
            if dur > slot * 1.2:
                df = max(0.5, slot / dur)  # IndexTTS 支持 0.5~2.0
                spk = seg.get("speaker", "SPEAKER_00")
                ref = refs.get(spk)
                if not ref:
                    continue
                retry.append({
                    "ref": ref, "text": seg["translated_text"], "lang": self.target_lang,
                    "out": str(out), "df": round(df, 2),
                })
        if retry:
            log.info("[TTS] %d 句配音过长，用 duration_factor 加速重合成", len(retry))
            synth.synth_batch(retry)

    # ---- 对齐（允许重叠）----
    def stage_align(self):
        if self.ws.exists("alignment.json"):
            log.info("[Alignment] alignment.json exists, skip")
            return self._load_json("alignment.json")["placements"]
        translation = self._load_json("translation.json")
        utterances = translation["utterances"]
        audio = self._load_json("tts_map.json")["audio"]
        if len(audio) != len(utterances):
            raise RuntimeError("[Alignment] tts_map 与 utterances 长度不一致")
        cfg = self.config.get("alignment", {})
        placements = aligner.align_and_render(
            utterances, audio, self.ws.path("aligned"),
            max_stretch=float(cfg.get("max_stretch", 0.15)),
            allow_overlap=True,
        )
        self._save_json("alignment.json", {"placements": placements})
        return placements

    # ---- 混音 ----
    def stage_mix(self):
        if self.ws.exists("final.wav"):
            log.info("[Mixing] final.wav exists, skip")
            return str(self.ws.path("final.wav"))
        placements = self._load_json("alignment.json")["placements"]
        bg = self.ws.path("background.wav")
        if not bg.exists():
            bg = self.ws.path("audio_hq.wav")
        vocals = self.ws.path("vocals.wav")
        cfg = self.config.get("mixing", {})
        out = self.ws.path("final.wav")
        audio_mixer.mix(
            bg, placements, out,
            original_vocal_path=str(vocals) if vocals.exists() else None,
            original_vocal_gain=float(cfg.get("original_vocal_gain", 0.08)),
            background_gain=float(cfg.get("background_gain", 1.0)),
            dubbed_gain=float(cfg.get("dubbed_gain", 1.0)),
        )
        return out

    # ---- 封装 ----
    def stage_mux(self):
        out = Path(self.output) if self.output else self.ws.path(f"{self.ws.name}_dubbed.mp4")
        if out.exists():
            log.info("[FFmpeg] output exists, skip")
            return str(out)
        final_audio = self.ws.path("final.wav")
        if not final_audio.exists():
            raise RuntimeError("[FFmpeg] final.wav 缺失，请先运行 --stage mix")
        # 烧录翻译字幕（若存在）；烧字幕需重编码视频
        subtitle_path = None
        if self.config.get("mixing", {}).get("burn_subtitles", True):
            for name in ("subtitles_translated.ass", "subtitles.ass"):
                p = self.ws.path(name)
                if p.exists():
                    subtitle_path = str(p)
                    break
        return mux_video(self.input_path, final_audio, out, copy_video=True, subtitle_path=subtitle_path)

    # ---- 分发 ----
    def run(self, stages):
        to_run = _STAGE_ORDER if "all" in stages else stages
        for s in to_run:
            fn = getattr(self, f"stage_{s}", None)
            if fn is None:
                raise ValueError(f"unknown stage: {s}")
            log.info("[Pipeline] === stage: %s ===", s)
            fn()
