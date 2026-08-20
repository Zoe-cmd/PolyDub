"""音频工具：时长、剪辑。"""
from pathlib import Path


def duration(path) -> float:
    import soundfile as sf

    return float(sf.info(str(path)).duration)


def cut(audio_path, start, end, out_path):
    """按时间范围剪辑音频（ffmpeg）。"""
    from ..video.extractor import run_ffmpeg

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        ["-i", str(audio_path), "-ss", str(start), "-to", str(end),
         "-c:a", "pcm_s16le", str(out_path)]
    )
    return str(out_path)
