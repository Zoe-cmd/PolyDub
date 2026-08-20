"""逐说话人转写（含重叠语音分离）。

流程：
1) 读取 diarization turns（谁在何时说话，可能重叠）。
2) 按重叠关系把 turns 聚成 clusters。
3) 单个 turn 的 cluster：直接切出该段人声 ASR。
4) 多个 turn 的 cluster（多人同时说话）：切出重叠段，用 SepFormer 分离成多路，
   再用说话人嵌入把每路匹配回对应说话人，分别 ASR。
5) 输出 utterances（[{speaker, start, end, text}]，允许时间重叠）。
"""
from pathlib import Path

import numpy as np

from ..utils.logging import get_logger
from ..utils.audio import cut

log = get_logger(__name__)


def overlap(a, b):
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def build_clusters(turns):
    """把相互重叠的 turns 聚成 clusters（同一 cluster 内不同说话人时间重叠）。"""
    turns = sorted(turns, key=lambda t: (t["start"], t["end"]))
    clusters = []
    for t in turns:
        for cl in clusters:
            if any(u["speaker"] != t["speaker"] and overlap(t, u) > 0 for u in cl):
                cl.append(t)
                break
        else:
            clusters.append([t])
    return clusters


class SpeakerEmbedding:
    """说话人嵌入（wespeaker，用于把分离出的音频流匹配回说话人）。"""

    def __init__(self, device="cuda"):
        import torch
        from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding

        self._model = PretrainedSpeakerEmbedding(
            "pyannote/wespeaker-voxceleb-resnet34-LM", device=torch.device(device)
        )

    def embed_file(self, wav_path):
        import torch
        import torchaudio
        import torchaudio.functional as F

        wav, sr = torchaudio.load(str(wav_path))
        wav = wav.mean(dim=0, keepdim=True)  # (1, samples)
        if sr != 16000:
            wav = F.resample(wav, sr, 16000)
        wav = wav.unsqueeze(0)  # (1, 1, samples) 加 batch 维度
        with torch.no_grad():
            emb = self._model(wav)
        emb = np.asarray(emb).reshape(-1)
        n = float(np.linalg.norm(emb))
        return emb / (n + 1e-8) if n > 0 else emb

    def close(self):
        from ..utils import gpu

        gpu.release(self._model)
        self._model = None


def assign_streams(stream_paths, speakers, ref_audio_map, embedding):
    """把分离出的多路音频匹配回说话人（按嵌入余弦相似度）。"""
    refs = {spk: embedding.embed_file(ref_audio_map[spk])
            for spk in speakers if ref_audio_map.get(spk)}

    # 参考不足时按顺序兜底分配
    if len(refs) != len(speakers) or not stream_paths:
        return {spk: stream_paths[i % len(stream_paths)]
                for i, spk in enumerate(speakers)} if stream_paths else {}

    assignment = {}
    used = set()
    for stream in stream_paths:
        emb = embedding.embed_file(stream)
        best_spk, best_sim = None, -1.0
        for spk, ref in refs.items():
            if spk in used:
                continue
            sim = float(np.dot(emb, ref))
            if sim > best_sim:
                best_sim, best_spk = sim, spk
        if best_spk is None:
            best_spk = next(s for s in speakers if s not in used)
        assignment[best_spk] = stream
        used.add(best_spk)
    return assignment


def _transcribe_file(transcriber, wav_path):
    from ..utils.audio import duration as _dur

    try:
        if _dur(wav_path) < 0.3:  # 跳过过短/空片段（faster-whisper 词级时间戳会崩）
            return None
    except Exception:
        pass
    segments, _meta = transcriber.transcribe(wav_path, word_timestamps=False)
    text = " ".join(s["text"] for s in segments).strip()
    return text or None


def build_utterances(vocals_path, turns, transcriber, separators, embedding, workdir, speakers_refs):
    """生成 utterances 列表，返回 (utterances, overlap_count)。

    separators: {2: SpeechSeparator(2mix), 3: SpeechSeparator(3mix)}（按重叠人数选模型）
    """
    clusters = build_clusters(turns)
    utterances = []
    overlap_count = sum(1 for cl in clusters if len(cl) > 1)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    def _add(speaker, start, end, text):
        if text:
            utterances.append({"speaker": speaker, "start": start, "end": end, "text": text})

    for idx, cl in enumerate(clusters):
        cstart = min(t["start"] for t in cl)
        cend = max(t["end"] for t in cl)

        if len(cl) == 1:
            t = cl[0]
            chunk = workdir / f"c{idx}_single.wav"
            cut(vocals_path, t["start"], t["end"], chunk)
            _add(t["speaker"], t["start"], t["end"], _transcribe_file(transcriber, chunk))
            continue

        # 多人重叠：分离后再分别 ASR
        speakers = sorted({t["speaker"] for t in cl})
        mix = workdir / f"c{idx}_mix.wav"
        cut(vocals_path, cstart, cend, mix)

        separator = (separators or {}).get(len(speakers))
        if separator is None:
            # 无对应人数的分离模型（如 4 人以上）：整体转写（退化）
            log.warning("[Utterances] cluster 有 %d 人重叠，无对应分离模型，整体转写", len(speakers))
            text = _transcribe_file(transcriber, mix)
            for t in cl:
                _add(t["speaker"], t["start"], t["end"], text)
            continue

        streams = separator.separate(mix, workdir / f"c{idx}", prefix="s")
        assignment = assign_streams(streams, speakers, speakers_refs, embedding)
        for spk, stream in assignment.items():
            t = next(t for t in cl if t["speaker"] == spk)
            _add(spk, t["start"], t["end"], _transcribe_file(transcriber, stream))

    utterances.sort(key=lambda u: (u["start"], u["end"]))
    log.info("[Utterances] %d 句（其中重叠簇 %d 个）", len(utterances), overlap_count)
    return utterances, overlap_count
