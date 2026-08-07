"""Wake-word detection via openWakeWord.

Runs continuously on streamed mic audio, cheaply (tiny ONNX models, single
thread each), so the Pi can sit listening all game without transcribing or
diarizing anything until a player actually says the wake word. That's the
point of this whole approach vs. the earlier diarization-based one: instead
of running heavy models on everything anyone says, we only wake up (and only
then spend a speaker-ID check, see speaker_id.py) on a deliberate trigger.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np

from .config import WakeWordConfig

log = logging.getLogger(__name__)

CHUNK_SAMPLES = 1280  # openWakeWord's native frame size: 80ms at 16 kHz


@dataclass
class WakeWordEvent:
    model: str
    score: float


class WakeWordDetector:
    def __init__(self, cfg: WakeWordConfig):
        import openwakeword
        from openwakeword.model import Model

        # openwakeword asks onnxruntime for CUDAExecutionProvider first and falls back to
        # CPU -- harmless on this GPU-less Pi, but noisy every time a session is created.
        warnings.filterwarnings("ignore", message=r"Specified provider 'CUDAExecutionProvider'",
                                 category=UserWarning)

        # openwakeword renamed this dict from `models` to `MODELS` at some point after
        # this code was written; 0.6.0 (the currently installed version) only has `MODELS`.
        if cfg.model not in openwakeword.MODELS:
            raise ValueError(
                f"Unknown wake word {cfg.model!r}; bundled options: {sorted(openwakeword.MODELS)}"
            )
        self.cfg = cfg
        model_path = openwakeword.MODELS[cfg.model]["model_path"]
        try:
            self._model = Model(wakeword_models=[model_path])
        except ValueError as e:
            # openwakeword's pip package ships no model weights at all -- MODELS just lists
            # their names/URLs. A fresh install needs a one-time download before any model
            # name resolves to a real file, which is what this actually was, however it reads.
            raise RuntimeError(
                "Couldn't load the wake word model -- if this is a fresh install, fetch the "
                "bundled model weights once with: python -c "
                "\"from openwakeword.utils import download_models; download_models()\". "
                f"Original error: {e}"
            ) from e
        self._model_name = next(iter(self._model.models))
        self._armed = True  # fires once per rise above threshold, not once per frame while held

    def process_chunk(self, chunk: np.ndarray) -> WakeWordEvent | None:
        """Feed one 80ms (1280-sample) int16 mono 16kHz chunk; returns an event on
        the frame where the score first crosses the threshold, else None."""
        score = float(self._model.predict(chunk)[self._model_name])
        detected = score >= self.cfg.threshold
        fire = detected and self._armed
        self._armed = not detected
        return WakeWordEvent(self._model_name, score) if fire else None
