"""Gradio Web 控制台：上传视频 / 从 URL 下载 → 选语言 → 分阶段/一键处理 → 下载配音视频。

启动：python webui.py  （可选 --port 7860 --host 0.0.0.0 --share）
"""
import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import gradio as gr
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pipeline.pipeline import Pipeline
from app.utils import gpu
from app.utils.env import load_dotenv, read_env, write_env
from app.settings import SETTINGS_SECTIONS, value_from_str, value_to_str

CONFIG_PATH = "config/config.yaml"
INPUTS_DIR = "inputs"
ENV_PATH = ".env"

# 点某阶段按钮 = 运行到该阶段为止的必需链条（依赖顺序）
STAGES_FOR = {
    "separate": ["extract", "separate"],
    "diarize": ["extract", "separate", "diarize"],
    "transcribe": ["extract", "separate", "diarize", "transcribe"],
    "translate": ["extract", "separate", "diarize", "transcribe", "translate"],
    "tts": ["extract", "separate", "diarize", "transcribe", "translate", "tts"],
    "align": ["extract", "separate", "diarize", "transcribe", "translate", "tts", "align"],
    "mix": ["extract", "separate", "diarize", "transcribe", "translate", "tts", "align", "mix"],
    "mux": ["extract", "separate", "diarize", "transcribe", "translate", "tts", "align", "mix", "mux"],
}

STAGE_LABEL = {
    "extract": "提取音频", "transcribe": "语音转文字", "diarize": "说话人分离",
    "separate": "人声/背景分离", "translate": "翻译", "tts": "TTS 配音",
    "align": "时间轴对齐", "mix": "混音", "mux": "封装视频",
}

LANGS = ["auto", "en", "zh", "ja", "ko", "es", "ar", "fr", "de", "ru"]
TARGET_LANGS = ["zh", "en", "ja", "es", "ar"]


load_dotenv(ENV_PATH)


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


def read_text(path):
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def read_json(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_upload(video_path):
    if not video_path:
        return None
    src = Path(video_path)
    os.makedirs(INPUTS_DIR, exist_ok=True)
    dst = Path(INPUTS_DIR) / src.name
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)
    return str(dst)


def build_info(p):
    lines = []
    t = read_json(p.ws.path("transcript.json"))
    meta = t.get("meta", {})
    if meta:
        lines.append(f"检测语言: {meta.get('language')} (置信 {meta.get('language_probability')})")
        lines.append(f"音频时长: {meta.get('duration', 0):.1f}s")
        lines.append(f"字幕句数: {len(t.get('segments', []))}")
    d = read_json(p.ws.path("diarization.json"))
    if d.get("speakers"):
        lines.append(f"说话人数: {len(d['speakers'])}  ({', '.join(d['speakers'])})")
    used = gpu.vram_used_mb()
    lines.append(f"GPU 显存占用: {used} MB" if used >= 0 else "GPU 显存占用: N/A")
    return "\n".join(lines)


def handle_download(url):
    """从 URL 下载视频到 downloads/，返回状态信息。"""
    if not url or not url.strip():
        return "❌ 请输入 URL"
    try:
        from app.video.downloader import download

        config = load_config()
        dl_cfg = config.get("download", {})
        fp, _info = download(
            url.strip(),
            dl_cfg.get("output_dir", "downloads"),
            cookies_config=dl_cfg.get("cookies"),
            show_progress=True,
        )
        return f"✅ 已下载到：{fp}"
    except Exception as e:
        return f"❌ 下载失败：{e}"


def apply_env_to_config(config):
    """把 .env 里的引擎配置映射到 config（供翻译阶段使用）。"""
    env = read_env(ENV_PATH)
    engine = (env.get("TRANSLATE_ENGINE") or "openai").strip().lower()
    if engine in ("openai", "api"):
        config.setdefault("translation", {})["backend"] = "api"
        api = config.setdefault("translation", {}).setdefault("api", {})
        if env.get("OPENAI_BASE_URL"):
            api["base_url"] = env.get("OPENAI_BASE_URL").strip()
        if env.get("TRANSLATE_MODEL"):
            api["model"] = env.get("TRANSLATE_MODEL").strip()
        key = env.get("OPENAI_API_KEY") or os.environ.get("VT_TRANSLATE_API_KEY")
        if key and key.strip():
            api["api_key"] = key.strip()
    else:
        config.setdefault("translation", {})["backend"] = "local"
    return config


def run_stages(video_path, stages, source_lang, target_lang, do_separate, num_speakers):
    """生成器：流水线在后台线程运行，每条日志经队列实时推送到页面。

    状态栏 = 当前阶段 + 进度 + 已用时；日志栏 = 各环节完整日志（实时滚动）。
    """
    import queue as _queue
    import threading
    import time as _time

    if not video_path:
        yield "❌ 请先上传视频", "", "", "", None
        return
    video_path = save_upload(video_path)

    q = _queue.Queue()
    status = {"text": "⏳ 准备中..."}
    log_lines = []

    class QueueHandler(logging.Handler):
        def emit(self, record):
            try:
                q.put(("LOG", self.format(record)))
            except Exception:
                pass

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    qh = QueueHandler()
    qh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
    root.addHandler(qh)

    result = {}

    def worker():
        try:
            config = apply_env_to_config(load_config())
            if str(num_speakers).strip().lower() != "auto":
                config.setdefault("diarization", {})["num_speakers"] = int(num_speakers)
            src = None if source_lang == "auto" else source_lang
            p = Pipeline(config, video_path, source_lang=src, target_lang=target_lang)

            run_list = [s for s in stages if not (s == "separate" and not do_separate)]
            total = max(len(run_list), 1)
            t0 = _time.time()
            for i, s in enumerate(run_list):
                label = STAGE_LABEL.get(s, s)
                status["text"] = f"▶ 正在执行：{label}（{i + 1}/{total}）｜已用时 {_time.time() - t0:.0f}s"
                logging.getLogger("webui").info("【%s】===== 开始（%d/%d）=====", label, i + 1, total)
                getattr(p, f"stage_{s}")()
                status["text"] = f"✅ 完成：{label}（{i + 1}/{total}）｜已用时 {_time.time() - t0:.0f}s"

            info = build_info(p)
            srt = read_text(p.ws.path("subtitles_speakers.srt")) or read_text(p.ws.path("subtitles.srt"))
            trans = read_text(p.ws.path("subtitles_translated.srt"))
            final = p.ws.path(f"{p.ws.name}_dubbed.mp4")
            final = str(final) if Path(final).exists() else None
            status["text"] = f"🎉 全部完成！总用时 {_time.time() - t0:.0f}s\n\n{info}"
            result["payload"] = (srt, trans, final)
        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            status["text"] = f"❌ 处理失败：{e}"
            logging.getLogger("webui").error("处理失败：%s\n%s", e, tb)
        finally:
            q.put(("DONE", None))

    threading.Thread(target=worker, daemon=True).start()

    try:
        while True:
            try:
                item = q.get(timeout=0.5)
            except _queue.Empty:
                yield status["text"], "\n".join(log_lines), "", "", None
                continue
            if item[0] == "DONE":
                break
            if item[0] == "LOG":
                log_lines.append(item[1])
                if len(log_lines) > 1000:  # 防止日志无限增长
                    log_lines = log_lines[-1000:]
                yield status["text"], "\n".join(log_lines), "", "", None
    finally:
        root.removeHandler(qh)

    srt, trans, final = result.get("payload", ("", "", None))
    yield status["text"], "\n".join(log_lines), srt, trans, final


def build_settings_tab():
    """渲染「设置」页内容（不含外层 gr.Tab，由调用方包裹）。"""
    env_vals = read_env(ENV_PATH)
    gr.Markdown("### 全局配置（鼠标悬停每个选项可查看说明；保存后同步到 .env 并立即生效）")

    components = []  # [(key, typ, component)]

    def render_items(items):
        for key, label, typ, choices, desc in items:
            if typ == "choice":
                default = env_vals.get(key, "")
                if default not in (choices or []):
                    default = (choices or [None])[0]
                c = gr.Dropdown(choices or [], value=default, label=label, info=desc)
            elif typ == "checkbox":
                c = gr.Checkbox(value=value_from_str(env_vals.get(key), "checkbox"), label=label, info=desc)
            elif typ == "number":
                c = gr.Number(value=value_from_str(env_vals.get(key), "number"), label=label, info=desc)
            elif typ == "textarea":
                c = gr.Textbox(value=env_vals.get(key, ""), label=label, lines=8, info=desc)
            else:
                c = gr.Textbox(
                    value=env_vals.get(key, ""),
                    label=label,
                    type="password" if typ == "password" else "text",
                    info=desc,
                )
            components.append((key, typ, c))

    # 左右两栏，缩短页面
    mid = (len(SETTINGS_SECTIONS) + 1) // 2
    with gr.Row():
        with gr.Column(scale=1):
            for section, items in SETTINGS_SECTIONS[:mid]:
                with gr.Accordion(section, open=False):
                    render_items(items)
        with gr.Column(scale=1):
            for section, items in SETTINGS_SECTIONS[mid:]:
                with gr.Accordion(section, open=False):
                    render_items(items)

    btn_save = gr.Button("💾 保存所有设置", variant="primary")
    save_status = gr.Textbox(label="保存结果", interactive=False, lines=1)

    def do_save(*values):
        updates = {}
        for (key, typ, _c), v in zip(components, values):
            if key in ("YOUTUBE_COOKIES_JSON", "TIKTOK_COOKIES_JSON"):
                # 粘贴的 cookie JSON 写到独立文件，.env 只存文件路径
                platform = "youtube" if "YOUTUBE" in key else "tiktok"
                target_key = f"{'YOUTUBE' if 'YOUTUBE' in key else 'TIKTOK'}_COOKIES_FILE"
                cookie_file = Path("config") / "cookies" / f"{platform}_cookies.txt"
                if v and str(v).strip():
                    cookie_file.parent.mkdir(parents=True, exist_ok=True)
                    cookie_file.write_text(str(v).strip(), encoding="utf-8")
                    updates[target_key] = str(cookie_file)
                else:
                    # 清空输入框且当前配置指向我们管理的文件时，删除该 cookie 文件
                    cur = env_vals.get(target_key, "")
                    if cur and str(cookie_file) in str(cur):
                        cookie_file.unlink(missing_ok=True)
                        updates[target_key] = ""
                continue
            new_str = value_to_str(v, typ)
            # 只保存用户改过的字段：避免把「页面构建后 .env 被外部修改的值」覆盖掉
            if new_str == env_vals.get(key, ""):
                continue
            updates[key] = new_str
        if not updates:
            return "✅ 无改动（所有设置与 .env 一致）"
        try:
            write_env(ENV_PATH, updates)
            load_dotenv(ENV_PATH, override=True)
            return "✅ 已保存改动到 .env 并立即生效"
        except Exception as e:
            return f"❌ 保存失败：{e}"

    btn_save.click(
        do_save,
        inputs=[c for _k, _t, c in components],
        outputs=[save_status],
    )


def build_ui():
    with gr.Blocks(title="AI 视频翻译与多说话人配音") as demo:
        gr.Markdown("# 🎬 AI 视频翻译与多说话人配音")

        with gr.Tabs():
            with gr.Tab("🎬 处理"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### ⬇ 从 URL 下载（或下方上传本地视频）")
                        url_box = gr.Textbox(label="视频 URL（YouTube/TikTok 等）", placeholder="https://...")
                        btn_dl = gr.Button("⬇ 下载到 downloads/")
                        dl_status = gr.Textbox(label="下载结果", lines=2, interactive=False)

                        gr.Markdown("### 📤 上传本地视频")
                        video = gr.File(
                            label="上传视频",
                            file_types=[".mp4", ".mkv", ".mov", ".avi", ".webm"],
                            type="filepath",
                        )
                        src_lang = gr.Dropdown(LANGS, value="auto", label="原语言")
                        tgt_lang = gr.Dropdown(TARGET_LANGS, value="zh", label="目标语言")
                        num_spk = gr.Dropdown(["auto"] + [str(i) for i in range(1, 11)], value="auto", label="说话人数")
                        do_sep = gr.Checkbox(value=True, label="人声/背景分离")

                        btn_full = gr.Button("▶ 一键全流程", variant="primary")
                        with gr.Row():
                            btn_stages = {}
                            for s in ["transcribe", "diarize", "separate", "translate", "tts", "align", "mix", "mux"]:
                                btn_stages[s] = gr.Button(STAGE_LABEL[s], size="sm")
                        info_box = gr.Textbox(label="状态", lines=7, interactive=False)

                    with gr.Column(scale=2):
                        log_box = gr.Textbox(label="日志", lines=20, interactive=False)
                        with gr.Tabs():
                            with gr.Tab("原字幕 SRT"):
                                srt_box = gr.Textbox(lines=18, interactive=False, show_label=False)
                            with gr.Tab("翻译字幕"):
                                trans_box = gr.Textbox(lines=18, interactive=False, show_label=False)
                            with gr.Tab("结果视频"):
                                out_video = gr.Video(label="配音视频")

                outputs = [info_box, log_box, srt_box, trans_box, out_video]
                inputs = [video, src_lang, tgt_lang, do_sep, num_spk]

                def make_handler(stages):
                    def handler(v, s, t, sep, ns):
                        yield from run_stages(v, stages, s, t, sep, ns)

                    return handler

                btn_dl.click(handle_download, inputs=[url_box], outputs=[dl_status])
                btn_full.click(make_handler(STAGES_FOR["mux"]), inputs=inputs, outputs=outputs)
                for s, b in btn_stages.items():
                    b.click(make_handler(STAGES_FOR[s]), inputs=inputs, outputs=outputs)

            with gr.Tab("⚙️ 设置"):
                build_settings_tab()

    return demo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--share", action="store_true")
    args = ap.parse_args()

    demo = build_ui()
    demo.queue(default_concurrency_limit=1)
    demo.launch(server_name=args.host, server_port=args.port, share=args.share)
