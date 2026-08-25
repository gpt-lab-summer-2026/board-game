"""Kokoro text-to-speech for the ghost.

The same ONNX weights the voice loop uses, loaded once and kept: synthesis is
CPU-bound and reloading a 325 MB model per line would make the ghost slower to
speak than to think.

Deliberately separate from `python/speak.py` rather than importing it. That file
belongs to the voice loop and runs under its own virtualenv; the ghost runs
under PlanarAlly's. Sharing the module would mean sharing the interpreter, and
these two processes are started independently on purpose -- the board should
still be drivable when the microphone side is not running.
"""
from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger(__name__)

# ../../models, not ../models: this package sits at board-game/dnd/voice and the
# weights are shared with the voice loop at board-game/models.
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

DEFAULT_VOICE = "af_heart"


class KokoroSpeaker:
    """Says a line out loud, blocking until it has finished.

    `narrate.Narrator` calls this from a worker thread and serialises the calls,
    so nothing here needs to be async -- but it does need to be safe to call
    from a thread that is not the one that built it, hence the lock around
    synthesis.
    """

    def __init__(self, voice: str = DEFAULT_VOICE, speed: float = 1.0) -> None:
        from kokoro_onnx import Kokoro  # noqa: PLC0415 - heavy, and optional

        for path in (MODEL_PATH, VOICES_PATH):
            if not os.path.exists(path):
                raise FileNotFoundError(f"missing Kokoro model file: {path}")

        self.voice = voice
        self.speed = speed
        self._lock = threading.Lock()
        self._kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
        log.info("kokoro ready (%s)", voice)

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        import sounddevice as sd  # noqa: PLC0415

        with self._lock:
            samples, rate = self._kokoro.create(text, voice=self.voice, speed=self.speed)
            sd.play(samples, rate)
            sd.wait()
