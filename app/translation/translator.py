"""翻译：第三方 API（OpenAI 兼容）为主，本地 opus-mt 兜底。

- backend='api'       : 上下文/语气/专名/角色一致的影视对白翻译，0 显存。
                       主模型失败时自动按 TRANSLATE_MODEL_FALLBACKS 降级，
                       全部失败再退回本地 opus-mt。
- backend='local'     : 离线 NMT（opus-mt en↔zh），逐句、无上下文。
"""
import json
import os
import re

from ..utils.logging import get_logger
from ..utils import gpu

log = get_logger(__name__)

LANG_NAMES = {
    "en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "es": "Spanish", "ar": "Arabic", "fr": "French", "de": "German",
    "ru": "Russian", "pt": "Portuguese", "it": "Italian",
}

_SYSTEM = (
    "You are a subtitle translator. Translate each line from {source} to {target}, "
    "natural and colloquial. "
    "Output ONLY a JSON array of strings, one per input line, in the same order. "
    "No explanations."
)


def _parse_json_array(content: str, n: int):
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        arr = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", content, re.S)
        if not m:
            raise RuntimeError(f"[Translation] cannot parse API response: {content[:300]}")
        arr = json.loads(m.group(0))
    if not isinstance(arr, list) or len(arr) != n:
        raise RuntimeError(
            f"[Translation] expected {n} translations, got {len(arr) if isinstance(arr, list) else type(arr).__name__}"
        )
    return [str(x).strip() for x in arr]


class APITranslator:
    def __init__(self, base_url, api_key, model, timeout=90, fallbacks=None):
        import requests

        self.requests = requests
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.fallbacks = [m for m in (fallbacks or []) if m and m != model]
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError(
                "[Translation] API key 缺失：请设置环境变量（见 config translation.api.api_key_env）。"
            )

    def _chat(self, messages, model):
        url = self.base_url + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages, "temperature": 0.3}
        resp = self.requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"[Translation] API {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]

    def translate_lines(self, lines, source_lang, target_lang, prev_context=None):
        src = LANG_NAMES.get(source_lang, source_lang)
        tgt = LANG_NAMES.get(target_lang, target_lang)
        system = _SYSTEM.format(source=src, target=tgt)
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(lines))
        ctx = ""
        if prev_context:
            ctx = "Previously translated context (for consistency):\n" + "\n".join(
                f"- {c}" for c in prev_context
            ) + "\n\n"
        user = f"{ctx}Translate these {len(lines)} lines:\n{numbered}"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err = None
        for model in [self.model] + self.fallbacks:
            try:
                content = self._chat(messages, model)
                return _parse_json_array(content, len(lines))
            except Exception as e:
                last_err = e
                log.warning("[Translation] 模型 %s 失败，尝试下一个：%s", model, str(e)[:100])
        raise RuntimeError(f"[Translation] 所有模型均失败：{last_err}")


class LocalTranslator:
    """离线 NMT：opus-mt（en↔zh）。"""

    _PAIR = {
        ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
        ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
    }

    def __init__(self, model=None, device="cuda"):
        self.model_id = model
        self.device = device
        self._pipe = None

    def _resolve(self, source_lang, target_lang):
        if self.model_id:
            return self.model_id
        m = self._PAIR.get((source_lang, target_lang))
        if not m:
            raise RuntimeError(
                f"[Translation] opus-mt 无 '{source_lang}->{target_lang}' 模型，"
                "请改用 api 后端或 NLLB。"
            )
        return m

    def _load(self, source_lang, target_lang):
        from transformers import pipeline

        model = self._resolve(source_lang, target_lang)
        log.info("[Translation] Loading NMT %s ...", model)
        self._pipe = pipeline(
            "translation", model=model,
            device=0 if self.device == "cuda" else -1,
        )
        log.info("[Translation] NMT loaded.")

    def translate_lines(self, lines, source_lang, target_lang, prev_context=None):
        if self._pipe is None:
            self._load(source_lang, target_lang)
        return [self._pipe(t, max_length=512)[0]["translation_text"] for t in lines]

    def close(self):
        gpu.release(self._pipe)
        self._pipe = None


class Translator:
    def __init__(self, config):
        import threading

        cfg = config.get("translation", {})
        self.backend = cfg.get("backend", "api")
        self._impl = None
        self._local = None
        self._local_lock = threading.Lock()
        # 并行翻译参数（可经 .env 或 config 配置）
        self.batch_size = int(os.environ.get("TRANSLATE_BATCH_SIZE") or cfg.get("batch_size", 50) or 50)
        self.max_workers = int(os.environ.get("TRANSLATE_MAX_WORKERS") or cfg.get("max_workers", 4) or 4)
        if self.backend == "api":
            api = cfg.get("api", {})
            key_env = api.get("api_key_env", "VT_TRANSLATE_API_KEY")
            api_key = (os.environ.get(key_env) or api.get("api_key")
                       or os.environ.get("OPENAI_API_KEY") or "")
            base_url = (api.get("base_url") or os.environ.get("OPENAI_BASE_URL")
                        or "https://api.deepseek.com/v1")
            model = (api.get("model") or os.environ.get("TRANSLATE_MODEL")
                     or "deepseek-chat")
            fallbacks = [m.strip() for m in (os.environ.get("TRANSLATE_MODEL_FALLBACKS") or "").split(",") if m.strip()]
            timeout = int(api.get("timeout") or 300)
            self._impl = APITranslator(base_url, api_key, model, timeout=timeout, fallbacks=fallbacks)
        elif self.backend == "local":
            local = cfg.get("local", {})
            self._impl = LocalTranslator(local.get("model"), local.get("device", "cuda"))
        elif self.backend == "llm_local":
            raise NotImplementedError("[Translation] backend 'llm_local' (Qwen) 预留，暂用 api/local")
        else:
            raise ValueError(f"unknown translation backend: {self.backend}")

    def _get_local(self):
        if self._local is None:
            self._local = LocalTranslator(None, "cuda")
        return self._local

    def _translate_batch(self, batch, source_lang, target_lang):
        """单批翻译：API（含备选模型链）→ 本地 opus-mt。"""
        try:
            return self._impl.translate_lines(batch, source_lang, target_lang)
        except Exception as e:
            log.warning("[Translation] API 全部模型失败，本批退回本地 opus-mt：%s", str(e)[:120])
            with self._local_lock:  # 本地模型非线程安全，需串行
                return self._get_local().translate_lines(batch, source_lang, target_lang)

    def translate(self, segments, source_lang, target_lang, batch_size=None, context_lines=0):
        """并行翻译多个批次：批次更大 + 多路同时请求，大幅提速。

        单批失败自动降级：API → 备选模型 → 本地 opus-mt → 保留原文。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        batch_size = int(batch_size or self.batch_size or 50)
        texts = [s["text"] for s in segments]
        if not texts:
            log.info("[Translation] 无待翻译内容")
            return segments
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        n = len(batches)
        results = [None] * n

        def run_batch(bi, batch):
            try:
                return self._translate_batch(batch, source_lang, target_lang)
            except Exception as e:
                log.warning("[Translation] 批次 %d 全部降级失败，保留原文：%s", bi + 1, str(e)[:120])
                return list(batch)  # 最后兜底：保留原文

        workers = max(1, min(self.max_workers, n))
        log.info("[Translation] 开始翻译：%d 句，分 %d 批（每批 %d 句），%d 路并行",
                 len(texts), n, batch_size, workers)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(run_batch, bi, b): bi for bi, b in enumerate(batches)}
            done = 0
            for fut in as_completed(futs):
                bi = futs[fut]
                results[bi] = fut.result()
                done += 1
                log.info("[Translation] 并行进度：%d/%d 批完成", done, n)

        out = [t for r in results for t in (r or [])][:len(segments)]
        for seg, t in zip(segments, out):
            seg["translated_text"] = t
        log.info("[Translation] 翻译完成：%d 段（%s 后端，%d 路并行）", len(segments), self.backend, workers)
        return segments

    def close(self):
        if self._impl is not None and hasattr(self._impl, "close"):
            self._impl.close()
        if self._local is not None and hasattr(self._local, "close"):
            self._local.close()
