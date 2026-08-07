"""Kokoro TTS outlet for SLM-style responses.

Takes whatever short response text the command handler produces -- "Player
1's turn processed", "you don't have enough money", an ambiguous-move
follow-up question, etc. -- and speaks it aloud, so players get an audible
answer without needing to read a screen. (See ui_server.py for the paired
on-screen text box.)
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = str(Path(__file__).parent / "models" / "kokoro-v1.0.onnx")
DEFAULT_VOICES_PATH = str(Path(__file__).parent / "models" / "voices-v1.0.bin")


class KokoroSpeaker:
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, voices_path: str = DEFAULT_VOICES_PATH,
                 voice: str = "af_heart", speed: float = 1.0, lead_in_seconds: float = 0.8):
        from kokoro_onnx import Kokoro  # lazy: heavy dependency (onnxruntime + phonemizer)

        if not Path(model_path).exists() or not Path(voices_path).exists():
            raise FileNotFoundError(
                f"Kokoro model files not found at {model_path!r} / {voices_path!r}. Download them "
                "from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0 "
                "(kokoro-v1.0.onnx and voices-v1.0.bin) and place them there."
            )
        self.voice = voice
        self.speed = speed
        # The Bluetooth speaker takes a beat to wake from idle once playback starts, and
        # that wake-up latency was eating into the start of the actual sentence instead of
        # silence. Leading with throwaway silence gives it something disposable to cut
        # into instead. 0.8s was enough in testing; bump it if it's still clipping speech.
        self.lead_in_seconds = lead_in_seconds
        log.info("Loading Kokoro TTS model...")
        self._kokoro = Kokoro(model_path, voices_path)

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        return self._kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")

    def speak(self, text: str) -> None:
        """Synthesize and play, blocking until done.

        Goes through the `pw-play` CLI rather than sounddevice/PortAudio: this
        Pi's ALSA output devices have repeatedly rejected PortAudio's format/
        channel negotiation directly (see the mic's identical history in
        audio.py), while PipeWire's own tools negotiate it correctly.
        """
        import subprocess
        import tempfile

        from .audio import save_wav

        samples, sr = self.synthesize(text)
        if self.lead_in_seconds > 0:
            silence = np.zeros(int(self.lead_in_seconds * sr), dtype=samples.dtype)
            samples = np.concatenate([silence, samples])
        log.info('Speaking: "%s"', text)
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            save_wav(f.name, samples, sr)
            subprocess.run(["pw-play", f.name], check=True)
