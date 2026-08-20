"""edge-tts TTS：免费、无需 Key（微软免费接口）。

支持多说话人按性别分配音色：
- 读取 .env 的 EDGE_TTS_AUTO_VOICE（默认 true）
- 开启且说话人 > 1 时：用 F0 中位数粗估每个说话人的性别，
  从 TTS_VOICE_<LANG>_MALE / TTS_VOICE_<LANG>_FEMALE 音色池依次分配；
- 否则使用单音色 TTS_VOICE_<LANG>。
"""
import asyncio
from pathlib import Path

from ..utils.logging import get_logger
from ..utils.env import read_env
from ..video.extractor import run_ffmpeg

log = get_logger(__name__)

DEFAULT_VOICE = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
}


def _estimate_gender(ref_audio_path):
    """用 F0 中位数粗估性别：>165Hz 女，否则男。无法估计默认男。"""
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(ref_audio_path), sr=16000, mono=True)
        f0, _, _ = librosa.pyin(y, fmin=60, fmax=500, sr=sr)
        med = float(np.nanmedian(f0))
        if np.isnan(med):
            return "male"
        return "female" if med > 165 else "male"
    except Exception:
        return "male"


def assign_edge_voices(segments, ref_paths, lang):
    """为每个说话人分配 edge-tts 音色，返回 {speaker: voice}。"""
    env = read_env()
    auto = (env.get("EDGE_TTS_AUTO_VOICE") or "true").strip().lower() in ("true", "1", "yes", "on")
    speakers = sorted({s.get("speaker", "SPEAKER_00") for s in segments})

    single = env.get(f"TTS_VOICE_{lang.upper()}") or DEFAULT_VOICE.get(lang) or DEFAULT_VOICE["zh"]

    if not auto or len(speakers) <= 1:
        log.info("[TTS] edge-tts 单音色：%s", single)
        return {spk: single for spk in speakers}

    male_pool = [v.strip() for v in
                 (env.get(f"TTS_VOICE_{lang.upper()}_MALE") or "").split(",") if v.strip()]
    female_pool = [v.strip() for v in
                   (env.get(f"TTS_VOICE_{lang.upper()}_FEMALE") or "").split(",") if v.strip()]
    if not male_pool and not female_pool:
        log.info("[TTS] edge-tts 无音色池，回退单音色：%s", single)
        return {spk: single for spk in speakers}

    male_idx, female_idx = 0, 0
    result = {}
    for spk in speakers:
        gender = _estimate_gender(ref_paths.get(spk)) if ref_paths.get(spk) else "male"
        if gender == "female" and female_pool:
            result[spk] = female_pool[female_idx % len(female_pool)]
            female_idx += 1
        elif male_pool:
            result[spk] = male_pool[male_idx % len(male_pool)]
            male_idx += 1
        else:
            pool = female_pool or male_pool
            result[spk] = pool[female_idx % len(pool)]
            female_idx += 1
    log.info("[TTS] edge-tts 音色分配：%s", result)
    return result


class EdgeTTS:
    def __init__(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            raise RuntimeError("[TTS] 未安装 edge-tts，请先 `pip install edge-tts`")

    def synth_batch(self, items):
        """items: [{text, lang, voice?, out}]，一次异步合成全部。输出转 wav。"""
        if not items:
            return []
        import edge_tts

        async def _run_all():
            for it in items:
                voice = it.get("voice") or DEFAULT_VOICE.get(it.get("lang")) or DEFAULT_VOICE["zh"]
                out = Path(it["out"])
                out.parent.mkdir(parents=True, exist_ok=True)
                mp3 = out.with_suffix(".mp3")
                await edge_tts.Communicate(it["text"], voice).save(str(mp3))
                run_ffmpeg(["-i", str(mp3), "-ac", "1", "-ar", "24000",
                            "-c:a", "pcm_s16le", str(out)])
                mp3.unlink(missing_ok=True)
                log.info("[TTS] edge-tts(%s) -> %s", voice, out.name)

        asyncio.run(_run_all())
        return [it["out"] for it in items]
