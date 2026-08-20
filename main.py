"""统一入口。

用法示例：
    # 直接处理本地视频
    python main.py --input input.mp4 --source-lang en --target-lang zh

    # 从 URL 下载后处理（自动识别 YouTube/TikTok 等，cookie 见 config.yaml）
    python main.py --input "https://www.youtube.com/watch?v=xxx" --target-lang zh

    # 仅下载不处理
    python main.py --input "https://www.tiktok.com/@xxx/video/xxx" --download-only

    # 单阶段调试
    python main.py --input input.mp4 --stage transcribe
    python main.py --input input.mp4 --stage diarize
    python main.py --input input.mp4 --stage separate
    python main.py --input input.mp4 --stage translate
    python main.py --input input.mp4 --stage tts
    python main.py --input input.mp4 --stage align
    python main.py --input input.mp4 --stage mix
    python main.py --input input.mp4 --stage mux
"""
import argparse
import os
import sys

import yaml

# Windows 控制台默认 GBK，输出中文会乱码；强制 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.utils.logging import setup_logging, get_logger
from app.utils.env import apply_env_to_config
from app.pipeline.pipeline import Pipeline

log = get_logger(__name__)

STAGES = "extract|transcribe|diarize|separate|translate|tts|align|mix|mux|all"


def load_dotenv(path=".env"):
    """加载 .env 到环境变量（不覆盖已存在的变量）。"""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_dotenv()  # 加载 .env（HF_TOKEN / VT_TRANSLATE_API_KEY 等）


def load_config(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def parse_args():
    p = argparse.ArgumentParser(description="AI 视频翻译与多说话人配音系统")
    p.add_argument("--input", required=True, help="输入视频路径 或 URL（http/https 自动下载）")
    p.add_argument("--download-only", action="store_true", help="仅下载（--input 为 URL 时）不处理")
    p.add_argument("--source-lang", default=None, help="原语言 (en/zh/ja/ko...；默认自动检测)")
    p.add_argument("--target-lang", default="zh", help="目标语言")
    p.add_argument("--output", default=None, help="输出视频路径（默认 outputs/<name>/<name>_dubbed.mp4）")
    p.add_argument("--stage", default="all", help=f"逗号分隔：{STAGES}")
    p.add_argument("--config", default="config/config.yaml", help="配置文件")
    p.add_argument("--device", default="cuda", help="cuda | cpu")
    p.add_argument("--compute-type", default="float16", help="float16 | int8 | int8_float16")
    p.add_argument("--asr-model", default=None, help="覆盖 ASR 模型")
    p.add_argument("--num-speakers", default="auto", help="说话人数（auto=自动检测，或指定数字如 3）")
    return p.parse_args()


def resolve_input(raw_input, config):
    """若 --input 是 URL，则先用 yt-dlp 下载，返回本地文件路径。"""
    from app.video.downloader import is_url, download

    if not is_url(raw_input):
        return raw_input

    dl_cfg = config.get("download", {})
    out_dir = dl_cfg.get("output_dir", "downloads")
    log.info("[Download] 检测到 URL，开始下载 ...")
    filepath, _info = download(
        raw_input,
        out_dir,
        cookies_config=dl_cfg.get("cookies"),
        format_spec=dl_cfg.get("format", "bestvideo+bestaudio/best"),
        show_progress=True,
    )
    log.info("[Download] 已下载 -> %s", filepath)
    return filepath


def main():
    args = parse_args()
    setup_logging()
    config = apply_env_to_config(load_config(args.config))

    # CLI 覆盖配置
    asr_cfg = config.setdefault("asr", {})
    asr_cfg["device"] = args.device
    asr_cfg["compute_type"] = args.compute_type
    if args.asr_model:
        asr_cfg["model"] = args.asr_model
    # 说话人数：auto=自动检测，数字=强制指定
    if str(args.num_speakers).strip().lower() == "auto":
        config.setdefault("diarization", {})["num_speakers"] = None
    else:
        config.setdefault("diarization", {})["num_speakers"] = int(args.num_speakers)

    input_path = resolve_input(args.input, config)
    if args.download_only:
        log.info("[Download] 仅下载模式，结束。")
        return

    stages = [s.strip() for s in args.stage.split(",") if s.strip()]
    if not stages:
        stages = ["all"]

    pipeline = Pipeline(
        config,
        input_path,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        output=args.output,
    )
    log.info("[Pipeline] input=%s stages=%s", input_path, stages)
    pipeline.run(stages)
    log.info("[Pipeline] Done. Workspace: %s", pipeline.ws.dir)


if __name__ == "__main__":
    main()
