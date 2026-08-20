"""重叠语音分离（Speech Separation）：多人同时说话 → 多路独立语音。

SpeechBrain SepFormer（sepformer-libri2mix，Apache-2.0，<1GB 显存）。
属于「触发式」高级阶段：仅对 Diarization 判定为 overlap 的片段执行，
不要对整段视频无脑跑（计算量高）。
模型懒加载：仅在 separate() 首次调用时才占显存。
"""
from pathlib import Path

from ..utils.logging import get_logger
from ..utils import gpu

log = get_logger(__name__)


class SpeechSeparator:
    def __init__(self, model: str = "speechbrain/sepformer-libri2mix", device: str = "cuda"):
        self.model_id = model
        self.device = device
        self._model = None

    def _load(self):
        from speechbrain.inference.separation import SepformerSeparation

        log.info("[Separation] Loading SepFormer %s ...", self.model_id)
        self._model = SepformerSeparation.from_hparams(
            source=self.model_id, run_opts={"device": self.device}
        )
        log.info("[Separation] SepFormer loaded.")

    def separate(self, audio_path, out_dir, prefix="speech"):
        """分离重叠语音，返回每路语音的文件路径列表。"""
        import torchaudio

        if self._model is None:
            self._load()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        log.info("[Separation] Separating overlapping speech ...")
        est = self._model.separate_file(path=str(audio_path))  # (batch, time, n_src)
        est = est.squeeze(0)       # (time, n_src)
        est = est.transpose(0, 1)  # (n_src, time)
        sr = int(self._model.hparams.sample_rate)
        paths = []
        for i in range(est.shape[0]):
            p = out_dir / f"{prefix}_{i}.wav"
            torchaudio.save(str(p), est[i].unsqueeze(0).cpu(), sr)
            paths.append(str(p))
        log.info("[Separation] wrote %d separated tracks", len(paths))
        return paths

    def close(self):
        gpu.release(self._model)
        self._model = None
