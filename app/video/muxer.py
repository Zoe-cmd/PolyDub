"""最终封装：原视频 + 配音音频 → 输出视频。可选烧录字幕（需重编码视频）。"""
import shutil
from pathlib import Path

from ..utils.logging import get_logger
from .extractor import run_ffmpeg

log = get_logger(__name__)


def mux(video_path, audio_path, out_path, copy_video=True, crf=18, subtitle_path=None):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sub_path = Path(subtitle_path) if subtitle_path else None
    if sub_path is not None and sub_path.exists():
        # 烧录字幕需要重编码视频；复制到安全文件名避免 ffmpeg 滤镜路径转义问题
        tmp_sub = Path("_burn_tmp.ass")
        shutil.copy2(sub_path, tmp_sub)
        sub_arg = str(tmp_sub).replace("\\", "/").replace(":", "\\:")
        args = [
            "-i", str(video_path), "-i", str(audio_path),
            "-vf", f"ass={sub_arg}",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", str(out_path),
        ]
        log.info("[FFmpeg] Rendering final video（烧录字幕，重编码）...")
        try:
            run_ffmpeg(args)
        finally:
            tmp_sub.unlink(missing_ok=True)
    else:
        args = ["-i", str(video_path), "-i", str(audio_path)]
        if copy_video:
            args += ["-c:v", "copy"]
        else:
            args += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p"]
        args += [
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", str(out_path),
        ]
        log.info("[FFmpeg] Rendering final video (copy_video=%s) ...", copy_video)
        run_ffmpeg(args)
    return str(out_path)
