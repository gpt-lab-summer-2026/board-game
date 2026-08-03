"""Microphone capture for the diarization test harness.

Records at the mic's native rate (48 kHz -- requesting 16 kHz straight from
ALSA is unreliable on hardware that doesn't support it natively) and resamples
down to 16 kHz mono float32 in software, which is what both faster-whisper and
pyannote expect.
"""
from __future__ import annotations

import logging
from math import gcd

import numpy as np

from .config import AudioConfig

log = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg

    def record_seconds(self, seconds: float) -> np.ndarray:
        import sounddevice as sd  # lazy: only needed when actually recording

        log.info("Recording %.1fs at %d Hz from device %s...",
                  seconds, self.cfg.capture_rate, self.cfg.device or "default")
        frames = int(seconds * self.cfg.capture_rate)
        audio = sd.rec(frames, samplerate=self.cfg.capture_rate, channels=self.cfg.channels,
                        dtype="float32", device=self.cfg.device)
        sd.wait()
        audio = audio.reshape(-1)
        return resample(audio, self.cfg.capture_rate, self.cfg.sample_rate)

    def stream_16k_chunks(self, chunk_samples: int = 1280):
        """Continuously yield int16 mono 16kHz chunks of `chunk_samples` for as long
        as the caller keeps iterating -- for wake-word listening, which needs a live
        stream rather than record_seconds()'s fixed-length blocking capture. Tearing
        down the loop (break / generator close) stops and closes the mic stream.
        """
        import queue

        import sounddevice as sd

        native_chunk = chunk_samples * self.cfg.capture_rate // self.cfg.sample_rate
        q: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("sounddevice status: %s", status)
            q.put(indata[:, 0].copy())

        stream = sd.InputStream(samplerate=self.cfg.capture_rate, channels=self.cfg.channels,
                                 dtype="float32", device=self.cfg.device, blocksize=native_chunk,
                                 callback=callback)
        stream.start()
        try:
            while True:
                block = resample(q.get(), self.cfg.capture_rate, self.cfg.sample_rate)
                yield (np.clip(block, -1.0, 1.0) * 32767).astype("int16")
        finally:
            stream.stop()
            stream.close()


def resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Polyphase-resample mono float32 audio (e.g. mic's 48 kHz -> Whisper's 16 kHz)."""
    if orig_sr == target_sr:
        return samples
    from scipy.signal import resample_poly  # lazy: only needed when rates actually differ

    g = gcd(orig_sr, target_sr)
    up, down = target_sr // g, orig_sr // g   # 48000 -> 16000 reduces to up=1, down=3
    return resample_poly(samples, up, down).astype("float32")


def save_wav(path: str, samples: np.ndarray, sample_rate: int) -> None:
    """Write float32 [-1, 1] mono samples as 16-bit PCM, stdlib-only (no soundfile dependency)."""
    import wave

    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype("int16")
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm16.tobytes())
