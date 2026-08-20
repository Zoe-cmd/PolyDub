"""TTS：IndexTTS 2.5（复用其独立 venv，通过子进程调用，避免依赖冲突）。

IndexTTS 支持 zh/en/ja/es/ar（不含韩语），提供 duration_factor 语速控制（对齐关键）。
批量合成：一次子进程加载模型（~6GB）合成全部片段，避免逐句反复加载。
"""
import json
import subprocess
import tempfile
from pathlib import Path

from ..utils.logging import get_logger

log = get_logger(__name__)

_SNIPPET_BATCH = """\
import json, sys
from indextts.infer_v2_5 import IndexTTS2
cfg, model_dir, manifest = sys.argv[1:4]
tts = IndexTTS2(cfg_path=cfg, model_dir=model_dir, use_bf16=True)
items = json.load(open(manifest, encoding="utf-8"))
for it in items:
    tts.infer(spk_audio_prompt=it["ref"], text=it["text"], lang=it["lang"],
              output_path=it["out"], duration_factor=float(it.get("df", 1.0)))
    print("OK", it["out"], flush=True)
print("SYNTH_DONE")
"""

# 目标语言 -> IndexTTS lang 代码
LANG_MAP = {"zh": "ZH", "en": "EN", "ja": "JA", "es": "ES", "ar": "AR"}


class IndexTTS:
    def __init__(
        self,
        indextts_dir,
        checkpoint_dir="checkpoints_25",
        venv_python=None,
        device="cuda",
    ):
        self.dir = Path(indextts_dir)
        self.ckpt = self.dir / checkpoint_dir
        self.cfg = self.ckpt / "config.yaml"
        self.python = venv_python or str(self.dir / ".venv" / "Scripts" / "python.exe")
        self.device = device
        if not self.cfg.exists():
            raise RuntimeError(f"[TTS] IndexTTS checkpoint not found: {self.cfg}")

    def synth_batch(self, items):
        """一次子进程合成全部片段。

        items: [{ref, text, lang, out, df?}]，lang 用 'zh/en/ja/es/ar' 小写码。
        """
        if not items:
            return []
        items = [dict(it) for it in items]
        for it in items:
            code = LANG_MAP.get(it["lang"])
            if code is None:
                raise RuntimeError(
                    f"[TTS] IndexTTS 不支持语言 '{it['lang']}'（支持 zh/en/ja/es/ar）"
                )
            it["lang"] = code
            Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
            manifest = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(_SNIPPET_BATCH)
            snippet = f.name

        cmd = [self.python, snippet, str(self.cfg), str(self.ckpt), manifest]
        log.info("[TTS] IndexTTS synth_batch (%d items)", len(items))
        import os

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"          # 强制子进程 UTF-8，避免 GBK 控制台编码崩溃
        env["PYTHONIOENCODING"] = "utf-8"
        n = len(items)
        tail = []
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
            )
            done = 0
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                tail.append(line)
                tail = tail[-10:]
                if line.startswith("OK "):
                    done += 1
                    log.info("[TTS] 配音进度：%d/%d 段", done, n)
                elif line == "SYNTH_DONE":
                    log.info("[TTS] 全部 %d 段合成完成", n)
                else:
                    log.info("[TTS] %s", line)
            proc.wait()
        finally:
            Path(snippet).unlink(missing_ok=True)
            Path(manifest).unlink(missing_ok=True)

        if proc.returncode != 0 or done != n:
            detail = "\n".join(tail)[-800:] or f"returncode={proc.returncode}"
            raise RuntimeError(f"[TTS] IndexTTS failed: {detail}")
        return [it["out"] for it in items]

    def synth(self, text, ref_audio, target_lang, out_wav, duration_factor=1.0):
        self.synth_batch(
            [{"ref": str(ref_audio), "text": text, "lang": target_lang,
              "out": str(out_wav), "df": duration_factor}]
        )
        return str(out_wav)


class Synthesizer:
    """TTS 门面：根据 .env 的 TTS_ENGINE 选择引擎（index / edge / azure）。"""

    def __init__(self, config):
        from ..utils.env import read_env

        cfg = config.get("tts", {})
        env = read_env()
        env_engine = (env.get("TTS_ENGINE") or "").strip().lower()
        engine = {"index": "indextts", "edge": "edge", "azure": "azure"}.get(env_engine)
        engine = engine or cfg.get("engine", "indextts")
        self.engine = engine

        if engine == "indextts":
            # .env 的 IndexTTS 路径优先（设置页可直接改），config 作兜底
            indextts_dir = env.get("INDEX_TTS_REPO_DIR") or cfg.get("indextts_dir")
            checkpoint_dir = env.get("INDEX_TTS_MODEL_DIR") or cfg.get("checkpoint_dir", "checkpoints_25")
            self._impl = IndexTTS(
                indextts_dir=indextts_dir,
                checkpoint_dir=checkpoint_dir,
                venv_python=cfg.get("venv_python"),
                device=cfg.get("device", "cuda"),
            )
        elif engine == "edge":
            from .edge_synthesizer import EdgeTTS

            self._impl = EdgeTTS()
        else:
            raise ValueError(f"unknown tts engine: {engine}")

    def synth_batch(self, items):
        return self._impl.synth_batch(items)

    def synth(self, text, ref_audio, target_lang, out_wav, duration_factor=1.0):
        if self.engine == "indextts":
            return self._impl.synth(text, ref_audio, target_lang, out_wav, duration_factor)
        return self._impl.synth_batch(
            [{"text": text, "lang": target_lang, "out": str(out_wav)}]
        )[0]
