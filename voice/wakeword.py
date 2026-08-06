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

        if cfg.model not in openwakeword.models:
            raise ValueError(
                f"Unknown wake word {cfg.model!r}; bundled options: {sorted(openwakeword.models)}"
            )
        self.cfg = cfg
        model_path = openwakeword.models[cfg.model]["model_path"]
        self._model = Model(wakeword_model_paths=[model_path])
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
