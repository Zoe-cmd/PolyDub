"""混音：背景轨 + 配音轨（+ 可选压低后的原人声）。纯 CPU numpy，不占显存。"""
from pathlib import Path

import numpy as np
import soundfile as sf

from ..utils.logging import get_logger

log = get_logger(__name__)

TARGET_SR = 44100


def _load(path, sr=TARGET_SR):
    y, s = sf.read(str(path), dtype="float32")
    if s != sr:
        import librosa

        if y.ndim == 1:
            y = librosa.resample(y, orig_sr=s, target_sr=sr)
        else:
            y = librosa.resample(y.T, orig_sr=s, target_sr=sr).T
    return y.astype(np.float32), sr


def _to_shape(y, n_ch):
    if y.ndim == 1:
        y = y[:, None]
    if y.shape[1] == n_ch:
        return y
    if n_ch == 2 and y.shape[1] == 1:
        return np.repeat(y, 2, axis=1)
    if n_ch == 1:
        return y.mean(axis=1, keepdims=True)
    return y


def _normalize_loudness(y, target_rms=0.12, max_peak=0.95):
    """把音频响度归一化到目标 RMS（忽略静音段），同时限制峰值。

    解决「有的配音大声、有的小声」：每段配音统一到相近的感知响度。
    """
    if y.size == 0:
        return y
    mono = y.mean(axis=1) if y.ndim == 2 else y
    mask = np.abs(mono) > 0.01
    if not mask.any():
        return y
    rms = float(np.sqrt(np.mean(mono[mask] ** 2)))
    if rms < 1e-6:
        return y
    gain = target_rms / rms
    peak = float(np.max(np.abs(mono)))
    if peak > 0 and peak * gain > max_peak:
        gain = max_peak / peak
    return y * gain


def mix(
    background_path,
    placements,
    out_path,
    original_vocal_path=None,
    original_vocal_gain=0.08,
    background_gain=1.0,
    dubbed_gain=1.0,
    dubbed_rms=0.12,
):
    """placements: [{start,end,audio}]（秒 + 音频路径）。返回 out_path。

    dubbed_rms: 每段配音归一化到的目标响度（0~1，越大越响，建议 0.1~0.15）。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bg, sr = _load(background_path)
    max_end = max([p["end"] for p in placements], default=0.0)
    bg_dur = bg.shape[0] / sr
    total_dur = max(bg_dur, max_end) + 0.5
    n = int(round(total_dur * sr))
    n_ch = bg.shape[1] if bg.ndim == 2 else 1
    buf = np.zeros((n, n_ch), dtype=np.float32)

    # 背景
    bg2 = _to_shape(bg, n_ch)
    e = min(bg2.shape[0], n)
    buf[:e] += bg2[:e] * background_gain

    # 配音（按 place 时间轴；每段先做响度归一化，保证音量一致）
    for p in placements:
        y, s = _load(p["audio"])
        y = _to_shape(y, n_ch)
        y = _normalize_loudness(y, target_rms=dubbed_rms, max_peak=0.95)
        i0 = int(round(p["start"] * sr))
        if i0 >= n:
            continue
        seg = y[: n - i0]
        buf[i0:i0 + seg.shape[0]] += seg * dubbed_gain

    # 原人声（压低后保留，可选）
    if original_vocal_path:
        v, _ = _load(original_vocal_path)
        v = _to_shape(v, n_ch)
        e = min(v.shape[0], n)
        buf[:e] += v[:e] * original_vocal_gain

    # 防爆音：超幅则整体压回
    peak = float(np.max(np.abs(buf))) if buf.size else 0.0
    if peak > 1.0:
        buf = buf / peak * 0.99

    sf.write(str(out_path), buf, sr)
    log.info("[Mixing] wrote %s (%.1fs, sr=%d, %dch)", out_path.name, total_dur, sr, n_ch)
    return str(out_path)
