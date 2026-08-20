"""说话人分离（Diarization）：谁在何时说话（不负责转写内容）。

默认 pyannote.audio 3.1（speaker-diarization-3.1，gated 模型需 HF token）。
SoulX-Duplug-0.6B 作为免 token 兜底（待接入其推理接口）。
模型懒加载：仅在 diarize() 首次调用时才占显存。
"""
from ..utils.logging import get_logger
from ..utils import gpu

log = get_logger(__name__)


class Diarizer:
    def __init__(
        self,
        backend: str = "pyannote",
        model: str = "pyannote/speaker-diarization-3.1",
        hf_token: str = None,
        device: str = "cuda",
        threshold: float = None,
    ):
        self.backend = backend
        self.model_id = model
        self.hf_token = hf_token
        self.device = device
        self.threshold = threshold
        self._pipeline = None

    def _load_pyannote(self):
        if not self.hf_token:
            raise RuntimeError(
                "[Diarization] pyannote 是 gated 模型，需要 HF token。"
                "请设置 HF_TOKEN 环境变量，或改用 backend='soulx-duplug'。"
            )
        from pyannote.audio import Pipeline
        import torch

        log.info("[Diarization] Loading %s ...", self.model_id)
        self._pipeline = Pipeline.from_pretrained(self.model_id, use_auth_token=self.hf_token)
        if self.threshold is not None:
            try:
                self._pipeline.instantiate({"clustering": {"threshold": self.threshold}})
                log.info("[Diarization] 聚类阈值设为 %.3f", self.threshold)
            except Exception as e:
                log.warning("[Diarization] 设置聚类阈值失败（忽略）：%s", e)
        self._pipeline.to(torch.device(self.device))
        log.info("[Diarization] pyannote loaded on %s", self.device)

    def diarize(self, audio_path, num_speakers=None, min_speakers=None, max_speakers=None):
        """返回 (turns, speakers)。turns=[{speaker,start,end}]，speakers=排序后的说话人标签列表。"""
        if self._pipeline is None:
            if self.backend == "pyannote":
                self._load_pyannote()
            elif self.backend == "soulx-duplug":
                raise NotImplementedError(
                    "[Diarization] backend 'soulx-duplug' 待接入（免 token 兜底方案）。"
                )
            else:
                raise ValueError(f"unknown diarization backend: {self.backend}")

        log.info("[Diarization] Detecting speakers ...")
        result = self._pipeline(
            str(audio_path),
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        turns = []
        for turn, _, speaker in result.itertracks(yield_label=True):
            turns.append(
                {
                    "speaker": speaker,
                    "start": round(float(turn.start), 3),
                    "end": round(float(turn.end), 3),
                }
            )
        speakers = sorted({t["speaker"] for t in turns})
        log.info("[Diarization] %d turns, speakers=%s", len(turns), speakers)
        return turns, speakers

    def close(self):
        gpu.release(self._pipeline)
        self._pipeline = None
