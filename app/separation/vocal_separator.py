"""人声/背景分离：Demucs htdemucs（约 2GB 显存，MIT）。

输出人声轨 + 背景轨（含背景音乐/环境音），供后续配音混音使用。
模型懒加载：仅在 separate() 首次调用时才占显存。
"""
from ..utils.logging import get_logger
from ..utils import gpu

log = get_logger(__name__)


class VocalSeparator:
    def __init__(self, model: str = "htdemucs", device: str = "cuda"):
        self.model_name = model
        self.device = device
        self._sep = None

    def _load(self):
        from demucs.api import Separator

        log.info("[Separation] Loading Demucs %s on %s ...", self.model_name, self.device)
        self._sep = Separator(model=self.model_name, device=self.device, progress=False)
        log.info("[Separation] Demucs loaded.")

    def separate(self, audio_path, vocals_out, background_out):
        """分离为 vocals / background，返回两个输出文件路径。"""
        import torch
        import torchaudio
        from pathlib import Path

        Path(vocals_out).parent.mkdir(parents=True, exist_ok=True)
        Path(background_out).parent.mkdir(parents=True, exist_ok=True)
        if self._sep is None:
            self._load()

        log.info("[Separation] Separating vocals / background ...")
        _origin, separated = self._sep.separate_audio_file(str(audio_path))
        sr = int(getattr(self._sep, "samplerate", 44100))

        vocals = separated["vocals"]
        # 背景 = 除 vocals 外的所有 stem 之和（drums+bass+other）
        no_vocals = sum(v for k, v in separated.items() if k != "vocals")

        torchaudio.save(str(vocals_out), vocals.cpu(), sr)
        torchaudio.save(str(background_out), no_vocals.cpu(), sr)
        log.info("[Separation] wrote vocals.wav / background.wav")
        return {"vocals": str(vocals_out), "background": str(background_out)}

    def close(self):
        gpu.release(self._sep)
        self._sep = None
