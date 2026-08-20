"""`.env` 文件读写与加载。"""
import os
from pathlib import Path


def load_dotenv(path=".env", override=False):
    """把 .env 加载到环境变量。override=False 不覆盖已存在变量。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if override or k not in os.environ:
                os.environ[k] = v


def read_env(path=".env"):
    """解析 .env 为 dict（注释掉的 `# KEY=value` 也读入，作为默认值）。"""
    values = {}
    if not os.path.exists(path):
        return values
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = s[1:].strip()
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def write_env(path=".env", updates=None):
    """更新 .env 中的键值。

    - 保留未知键与注释结构；
    - 更新已知键的值；
    - 值为空时把该键转成注释（`# KEY=`）。
    """
    updates = updates or {}
    p = Path(path)
    if not p.exists():
        lines = [f"{k}={v}" for k, v in updates.items() if v]
        p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return

    def _key_of(s):
        s = s.strip()
        if s.startswith("#"):
            s = s[1:].strip()
        return s.split("=", 1)[0].strip() if "=" in s else None

    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    seen = set()
    for line in lines:
        k = _key_of(line)
        if k and k in updates:
            seen.add(k)
            v = updates[k]
            if v:
                out.append(f"{k}={v}")
            else:
                out.append(f"# {k}=")
            continue
        out.append(line)

    for k, v in updates.items():
        if k not in seen and v:
            out.append(f"{k}={v}")

    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def apply_env_to_config(config, env=None):
    """把 .env 里的引擎配置映射到 config（翻译后端 + API 参数）。

    - TRANSLATE_ENGINE=openai → translation.backend=api（用 OPENAI_API_KEY/BASE_URL/MODEL）
    - 其它 → translation.backend=local
    """
    env = env if env is not None else read_env()
    config = config or {}
    engine = (env.get("TRANSLATE_ENGINE") or "").strip().lower()
    tr = config.setdefault("translation", {})
    if engine in ("openai", "api"):
        tr["backend"] = "api"
        api = tr.setdefault("api", {})
        if env.get("OPENAI_BASE_URL"):
            api["base_url"] = env["OPENAI_BASE_URL"].strip()
        if env.get("TRANSLATE_MODEL"):
            api["model"] = env["TRANSLATE_MODEL"].strip()
        key = env.get("OPENAI_API_KEY") or os.environ.get("VT_TRANSLATE_API_KEY")
        if key:
            api["api_key"] = key.strip()
    else:
        tr["backend"] = "local"
    return config
