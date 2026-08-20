"""统一日志：每个阶段用 [Stage] 前缀输出清晰日志。"""
import logging
import sys

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    _configured = True


def get_logger(name: str = "pipeline") -> logging.Logger:
    return logging.getLogger(name)
