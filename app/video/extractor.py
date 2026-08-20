"""视频/音频提取与探测，基于 FFmpeg/ffprobe。"""
import subprocess
from pathlib import Path

from ..utils.logging import get_logger

log = get_logger(__name__)


def run_ffmpeg(args, tag="[Video]"):
    """执行 ffmpeg，失败抛出带说明的异常。"""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + list(args)
    log.debug("$ %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"{tag} ffmpeg failed: {msg}\ncmd: {' '.join(cmd)}")
    return proc


def extract_audio(video_path, out_wav, sample_rate=16000, channels=1) -> Path:
    """从视频提取音频为 PCM WAV（默认 16kHz 单声道，供 ASR/说话人用）。"""
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    log.info("[Video] Extracting audio -> %s (%dHz, %dch)", out_wav.name, sample_rate, channels)
    run_ffmpeg(
        [
            "-i", str(video_path),
            "-vn",
            "-ac", str(channels),
            "-ar", str(sample_rate),
            "-c:a", "pcm_s16le",
            str(out_wav),
        ]
    )
    return out_wav


def extract_audio_hq(video_path, out_wav, sample_rate=44100, channels=2) -> Path:
    """提取高保真音频（44.1kHz 立体声，供人声/背景分离用）。"""
    return extract_audio(video_path, out_wav, sample_rate=sample_rate, channels=channels)


def probe_duration(media_path) -> float:
    """用 ffprobe 获取媒体时长（秒）。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"[Video] ffprobe failed: {proc.stderr.strip()}")
    try:
        return float(proc.stdout.strip())
    except ValueError:
        raise RuntimeError(f"[Video] cannot parse duration: {proc.stdout!r}")
