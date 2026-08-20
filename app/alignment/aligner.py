"""音频时长对齐：让 TTS 配音匹配原始时间槽，且不覆盖下一句。

策略（优先级从高到低）：
1) TTS 时长 <= 槽长：末尾静音填充到槽内，保持原始起始时间（mode=pad）。
2) 略超（在 max_stretch 允许的压缩范围内）：time-stretch 压缩进槽内（mode=stretch）。
3) 仍超：保留原时长，全局把该句及后续句整体后移（字幕时间微调），保证不重叠（mode=overflow）。
更激进的「重新合成」（用 duration_factor<1）由 pipeline 在 TTS 阶段迭代。
纯 CPU DSP，不占显存。
"""
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from ..utils.logging import get_logger
from ..utils.audio import duration as _duration

log = get_logger(__name__)


def pad_to(audio_path, out_path, target_duration):
    """末尾补静音到 target_duration。"""
    y, sr = sf.read(str(audio_path), dtype="float32")
    target_n = int(round(target_duration * sr))
    n = y.shape[0]
    if n >= target_n:
        sf.write(str(out_path), y, sr)
        return str(out_path)
    if y.ndim == 1:
        pad = np.zeros(target_n - n, dtype=np.float32)
        out = np.concatenate([y, pad])
    else:
        pad = np.zeros((target_n - n, y.shape[1]), dtype=np.float32)
        out = np.concatenate([y, pad], axis=0)
    sf.write(str(out_path), out, sr)
    return str(out_path)


def time_stretch(audio_path, out_path, ratio):
    """ratio = 目标时长/原始时长（<1 加速压缩）。相位声码器，尽量不改变音高。"""
    y, sr = librosa.load(str(audio_path), sr=None, mono=False)  # (c, n)
    y_st = librosa.effects.time_stretch(y, rate=ratio)          # (c, n')
    sf.write(str(out_path), y_st.T, sr)
    return str(out_path)


def align_and_render(segments, audio_paths, out_dir, max_stretch=0.15, allow_overlap=False):
    """segments 与 audio_paths 等长。返回 placement 列表。

    placement = {index,start,end,audio,mode,ratio,orig_start,orig_end}
    audio 为已渲染的最终音频文件路径。
    allow_overlap=True 时保留原始重叠时间（多人同时说话），不做全局后移。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 第一遍：逐句计算 mode/ratio/起止
    raw = []
    for i, (seg, ap) in enumerate(zip(segments, audio_paths)):
        slot = max(0.0, seg["end"] - seg["start"])
        dur = _duration(ap)
        if dur <= slot:
            mode, ratio, start, end = "pad", 1.0, seg["start"], seg["end"]
        elif (slot / dur) >= (1 - max_stretch):
            mode, ratio, start, end = "stretch", slot / dur, seg["start"], seg["end"]
        else:
            mode, ratio, start, end = "overflow", 1.0, seg["start"], seg["start"] + dur
        raw.append(
            {
                "index": i, "start": start, "end": end, "mode": mode, "ratio": ratio,
                "src": ap, "orig_start": seg["start"], "orig_end": seg["end"],
            }
        )

    # 第二遍：全局消重叠（保持顺序，后移）；多人重叠场景需保留重叠则不执行
    if not allow_overlap:
        for i in range(1, len(raw)):
            prev_end = raw[i - 1]["end"]
            if raw[i]["start"] < prev_end:
                shift = prev_end - raw[i]["start"]
                raw[i]["start"] += shift
                raw[i]["end"] += shift

    # 第三遍：渲染音频
    placements = []
    for r in raw:
        out = out_dir / f"seg_{r['index']:04d}.wav"
        if r["mode"] == "stretch":
            time_stretch(r["src"], out, r["ratio"])
        elif r["mode"] == "pad":
            pad_to(r["src"], out, r["end"] - r["start"])
        else:  # overflow
            out = Path(r["src"])
        placements.append(
            {
                "index": r["index"], "start": r["start"], "end": r["end"],
                "audio": str(out), "mode": r["mode"], "ratio": r["ratio"],
                "orig_start": r["orig_start"], "orig_end": r["orig_end"],
            }
        )

    counts = {m: sum(1 for p in placements if p["mode"] == m) for m in {"pad", "stretch", "overflow"}}
    log.info("[Alignment] %d segments placed: %s", len(placements), counts)
    return placements
