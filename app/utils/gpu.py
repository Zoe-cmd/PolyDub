"""GPU 显存管理：模型按阶段加载/释放，避免多个大模型常驻。"""
import gc
import logging

log = logging.getLogger(__name__)


def configure_torch(disable_cudnn: bool = True) -> None:
    """进程内统一配置 torch。

    1) 禁用 cuDNN：faster-whisper 走 CTranslate2 的 CUDA 运行时，同进程内
       再加载 torch+cuDNN 会触发 "Could not load symbol cudnnGetLibConfig" 冲突。
    2) 打 speechbrain 懒加载补丁：pytorch_lightning 的 inspect.stack() 遍历调用栈时，
       访问 speechbrain 懒加载模块的 __file__ 会触发 k2_fsa 等缺失子模块导入并抛 ImportError，
       导致 pyannote 加载崩溃；转成 AttributeError 后 hasattr 可优雅跳过。
    """
    try:
        import torch

        if disable_cudnn:
            torch.backends.cudnn.enabled = False
    except Exception:
        pass
    _patch_speechbrain_lazy()


def _patch_speechbrain_lazy() -> None:
    try:
        from speechbrain.utils import importutils
    except Exception:
        return
    cls = importutils.LazyModule
    if getattr(cls, "_vt_lazy_patched", False):
        return
    try:
        orig = cls.__getattr__
    except AttributeError:
        return

    def _safe_getattr(self, attr):
        try:
            return orig(self, attr)
        except ImportError:
            raise AttributeError(attr) from None

    cls.__getattr__ = _safe_getattr
    cls._vt_lazy_patched = True


def release(*objects) -> None:
    """删除对象并释放 CUDA 显存。"""
    for obj in objects:
        if obj is not None:
            try:
                del obj
            except Exception:
                pass
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    except Exception:
        pass


def vram_used_mb() -> int:
    """返回当前 CUDA 显存占用（MB），失败返回 -1。"""
    try:
        import torch

        if not torch.cuda.is_available():
            return -1
        return int(torch.cuda.memory_allocated() / (1024 * 1024))
    except Exception:
        return -1
