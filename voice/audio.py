"""Microphone capture for the diarization test harness.

Goes through PipeWire's own `pw-record` CLI rather than sounddevice/
PortAudio: on this Pi, PortAudio's ALSA backend has repeatedly failed against
the same USB mic in different ways across this project's history --
"Invalid number of channels", "Invalid sample rate", devices silently
vanishing from its enumeration, "Error queueing device" -- while `pw-record`
negotiates through PipeWire correctly every time the underlying hardware node
itself is healthy. (A wedged PipeWire node -- visible via `pw-top` showing
state 'E' on the mic's node -- is a separate, hardware/driver-level failure
that needs a physical USB replug; no software fix here addresses that.)

Records at the mic's native rate (48 kHz -- requesting 16 kHz straight from
ALSA is unreliable on hardware that doesn't support it natively) and resamples
down to 16 kHz mono float32 in software, which is what both faster-whisper and
pyannote expect.
"""
from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import tempfile
import wave
from math import gcd

import numpy as np

from .config import AudioConfig

log = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        # pw-record is Linux/PipeWire-only -- never present on macOS, which has no
        # PipeWire at all. This dev-machine fallback goes through ffmpeg's avfoundation
        # input instead, purely so wake-word/speaker-ID/STT can be exercised off the Pi.
        # It doesn't replace pw-record's role there: whenever pw-record IS on PATH (i.e.
        # on the Pi), it's used, unconditionally.
        self._backend = "pw-record" if shutil.which("pw-record") else "ffmpeg"
        if self._backend == "ffmpeg":
            log.info("pw-record not found; capturing via ffmpeg (avfoundation) instead")

    def record_seconds(self, seconds: float) -> np.ndarray:
        log.info("Recording %.1fs at %d Hz...", seconds, self.cfg.capture_rate)
        if self._backend == "ffmpeg":
            return self._record_seconds_ffmpeg(seconds)
        return self._record_seconds_pw(seconds)

    def _record_seconds_pw(self, seconds: float) -> np.ndarray:
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            proc = subprocess.Popen(
                ["pw-record", "--rate", str(self.cfg.capture_rate),
                 "--channels", str(self.cfg.channels), f.name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                proc.wait(timeout=seconds)  # pw-record never exits on its own, so this always
            except subprocess.TimeoutExpired:  # times out -- that's the normal path, not an error
                # pw-record only flushes a valid WAV header/footer on SIGINT, not SIGTERM/kill.
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=5)
            with wave.open(f.name, "rb") as wav:
                raw = wav.readframes(wav.getnframes())
        audio = np.frombuffer(raw, dtype="int16").astype("float32") / 32768.0
        return resample(audio, self.cfg.capture_rate, self.cfg.sample_rate)

    def _record_seconds_ffmpeg(self, seconds: float) -> np.ndarray:
        # Unlike pw-record, ffmpeg exits on its own once -t elapses -- no SIGINT dance
        # needed to get a valid WAV footer.
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            subprocess.run(
                ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
                 "-f", "avfoundation", "-i", f":{self.cfg.mac_input_device}",
                 "-t", str(seconds),
                 "-ar", str(self.cfg.capture_rate), "-ac", str(self.cfg.channels),
                 f.name],
                check=True,
            )
            with wave.open(f.name, "rb") as wav:
                raw = wav.readframes(wav.getnframes())
        audio = np.frombuffer(raw, dtype="int16").astype("float32") / 32768.0
        return resample(audio, self.cfg.capture_rate, self.cfg.sample_rate)

    def stream_16k_chunks(self, chunk_samples: int = 1280):
        """Continuously yield int16 mono 16kHz chunks of `chunk_samples` for as long
        as the caller keeps iterating -- for wake-word listening, which needs a live
        stream rather than record_seconds()'s fixed-length blocking capture. Tearing
        down the loop (break / generator close) stops the capture process.
        """
        if self._backend == "ffmpeg":
            yield from self._stream_ffmpeg(chunk_samples)
        else:
            yield from self._stream_pw(chunk_samples)

    def _stream_pw(self, chunk_samples: int):
        native_chunk = chunk_samples * self.cfg.capture_rate // self.cfg.sample_rate
        bytes_per_chunk = native_chunk * 2  # s16 = 2 bytes/sample, mono
        proc = subprocess.Popen(
            ["pw-record", "--rate", str(self.cfg.capture_rate), "--channels", str(self.cfg.channels),
             "--format", "s16", "-a", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            while True:
                raw = proc.stdout.read(bytes_per_chunk)
                if len(raw) < bytes_per_chunk:
                    log.warning("pw-record stream ended unexpectedly")
                    break
                native = np.frombuffer(raw, dtype="int16").astype("float32") / 32768.0
                chunk = resample(native, self.cfg.capture_rate, self.cfg.sample_rate)
                yield (np.clip(chunk, -1.0, 1.0) * 32767).astype("int16")
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def _stream_ffmpeg(self, chunk_samples: int):
        native_chunk = chunk_samples * self.cfg.capture_rate // self.cfg.sample_rate
        bytes_per_chunk = native_chunk * 2  # s16 = 2 bytes/sample, mono
        proc = subprocess.Popen(
            ["ffmpeg", "-nostdin", "-loglevel", "error",
             "-f", "avfoundation", "-i", f":{self.cfg.mac_input_device}",
             "-ar", str(self.cfg.capture_rate), "-ac", str(self.cfg.channels),
             "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        try:
            while True:
                raw = proc.stdout.read(bytes_per_chunk)
                if len(raw) < bytes_per_chunk:
                    log.warning("ffmpeg stream ended unexpectedly")
                    break
                native = np.frombuffer(raw, dtype="int16").astype("float32") / 32768.0
                chunk = resample(native, self.cfg.capture_rate, self.cfg.sample_rate)
                yield (np.clip(chunk, -1.0, 1.0) * 32767).astype("int16")
        finally:
            # Unlike pw-record, ffmpeg reading an avfoundation session doesn't reliably
            # exit on SIGTERM alone -- observed hanging past a 5s wait in testing.
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


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
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767).astype("int16")
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm16.tobytes())
