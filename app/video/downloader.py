"""视频下载：基于 yt-dlp。支持 YouTube / TikTok 等站点。

cookie 来源（按优先级）：
- YouTube: config.yaml `download.cookies.youtube` → 环境变量 `YOUTUBE_COOKIES_FILE`
- TikTok:  config.yaml `download.cookies.tiktok` → 环境变量 `TIKTOK_COOKIES_BROWSER`（浏览器名，如 edge）
"""
import os
from pathlib import Path
from urllib.parse import urlparse

from ..utils.logging import get_logger

log = get_logger(__name__)


def is_url(text) -> bool:
    return str(text).startswith(("http://", "https://"))


def _build_cookie_opts(url, cookies_config):
    """根据 URL 域名构造 yt-dlp 的 cookie 相关 opts。

    cookie 来源优先级：
    - config.yaml `download.cookies.<platform>`（高级）
    - 环境变量 `YOUTUBE_COOKIES_FILE` / `TIKTOK_COOKIES_FILE`（设置页粘贴 JSON 后自动写入的路径）
    - TikTok 备选：`TIKTOK_COOKIES_BROWSER`（从浏览器读取登录 cookie）
    """
    cookies_config = cookies_config or {}
    domain = (urlparse(str(url)).netloc or "").lower()
    opts = {}
    if "youtube.com" in domain or "youtu.be" in domain:
        cf = (cookies_config.get("youtube") or None) or os.environ.get("YOUTUBE_COOKIES_FILE") or None
        if cf:
            opts["cookiefile"] = str(cf)
    elif "tiktok.com" in domain:
        cf = (cookies_config.get("tiktok") or None) or os.environ.get("TIKTOK_COOKIES_FILE") or None
        if cf:
            opts["cookiefile"] = str(cf)
        else:
            browser = os.environ.get("TIKTOK_COOKIES_BROWSER") or None
            if browser:
                opts["cookiesfrombrowser"] = (browser.strip(),)
    return opts


# yt-dlp 报错中与「需要登录/被风控」相关的关键词
_COOKIE_ERROR_HINTS = (
    "sign in to confirm", "you're not a bot", "not a bot",
    "login required", "log in", "only available to members",
    "confirm your age", "verify you are human", "bot check",
    "http error 403",
)


def _is_cookie_error(err_text: str) -> bool:
    t = (err_text or "").lower()
    return any(h in t for h in _COOKIE_ERROR_HINTS)


def _progress(d):
    """yt-dlp 进度回调（记录到日志）。"""
    status = d.get("status")
    if status == "downloading":
        pct = (d.get("_percent_str") or "").strip()
        speed = (d.get("_speed_str") or "").strip()
        eta = (d.get("_eta_str") or "").strip()
        log.info("[Download] %s %s ETA %s", pct, speed, eta)
    elif status == "finished":
        log.info("[Download] 下载完成，正在合并封装 ...")


def download(url, out_dir, cookies_config=None, format_spec="bestvideo+bestaudio/best",
             show_progress=False):
    """下载视频到 out_dir，返回 (文件路径, info)。失败抛异常。"""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        raise RuntimeError("[Download] 未安装 yt-dlp，请先 `pip install yt-dlp`")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cookie_opts = _build_cookie_opts(url, cookies_config)
    if cookie_opts.get("cookiefile") and not Path(cookie_opts["cookiefile"]).exists():
        log.warning("[Download] cookie 文件不存在，已忽略：%s", cookie_opts["cookiefile"])
        cookie_opts.pop("cookiefile")

    opts = {
        "outtmpl": str(out_dir / "%(title)s [%(id)s].%(ext)s"),
        "format": format_spec,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }
    opts.update(cookie_opts)
    if show_progress:
        opts["progress_hooks"] = [_progress]

    log.info("[Download] 开始下载 %s", url)
    if cookie_opts.get("cookiefile"):
        log.info("[Download] 使用 cookie：%s", cookie_opts["cookiefile"])
    if cookie_opts.get("cookiesfrombrowser"):
        log.info("[Download] 使用浏览器 cookie：%s", cookie_opts["cookiesfrombrowser"][0])

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        if _is_cookie_error(str(e)):
            raise RuntimeError(
                "[Download] 下载失败：可能需要登录 Cookie（被风控/需登录/会员/年龄限制）。\n"
                "解决办法：在 Web UI「设置」页 →『下载 Cookie（YouTube / TikTok）』中，"
                "用浏览器插件 Cookie-Editor 导出对应网站的 cookie（JSON）整段粘贴保存后重试。"
            ) from e
        raise

    filepath = None
    if info:
        rd = info.get("requested_downloads") or []
        if rd:
            filepath = rd[-1].get("filepath")
        if not filepath:
            filepath = ydl.prepare_filename(info)

    if not filepath or not Path(filepath).exists():
        raise RuntimeError(f"[Download] 下载失败：未找到输出文件（url={url}）")

    log.info("[Download] 完成 -> %s", filepath)
    return str(filepath), info
