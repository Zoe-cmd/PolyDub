"""ASR：基于 faster-whisper（CTranslate2 + CUDA）。"""
import math

from ..utils.logging import get_logger
from ..utils import gpu

log = get_logger(__name__)


class Transcriber:
    def __init__(
        self,
        model_size: str = "Systran/faster-whisper-large-v3",
        device: str = "cuda",
        compute_type: str = "float16",
        language: str = None,
        beam_size: int = 5,
        vad_filter: bool = False,
    ):
        self.model_size = model_size
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = None

        log.info(
            "[ASR] Loading model %s (device=%s, compute=%s) ...",
            model_size, device, compute_type,
        )
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        log.info("[ASR] Model loaded.")

    def transcribe(self, audio_path, word_timestamps=True):
        log.info("[ASR] Transcribing %s ...", audio_path)
        segments, info = self._model.transcribe(
            str(audio_path),
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            word_timestamps=word_timestamps,
        )

        results = []
        for s in segments:
            words = []
            for w in (s.words or []):
                words.append(
                    {
                        "word": w.word,
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                        "prob": round(float(w.probability), 4),
                    }
                )
            avg_logprob = float(s.avg_logprob)
            results.append(
                {
                    "start": round(float(s.start), 3),
                    "end": round(float(s.end), 3),
                    "text": s.text.strip(),
                    "avg_logprob": round(avg_logprob, 4),
                    # avg_logprob 是负的对数概率，exp 后作为粗略置信度(0,1]
                    "confidence": round(math.exp(min(avg_logprob, 0.0)), 4),
                    "words": words,
                }
            )

        meta = {
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4),
            "duration": round(float(info.duration), 3),
        }
        log.info(
            "[ASR] language=%s (prob=%.3f), %d segments, audio %.1fs",
            info.language, info.language_probability, len(results), info.duration,
        )
        return results, meta

    def close(self) -> None:
        log.info("[ASR] Releasing model ...")
        gpu.release(self._model)
        self._model = None
