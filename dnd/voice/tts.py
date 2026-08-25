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
import re
import shutil
import subprocess
import threading
import time

log = logging.getLogger(__name__)

# ../../models, not ../models: this package sits at board-game/dnd/voice and the
# weights are shared with the voice loop at board-game/models.
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

DEFAULT_VOICE = "af_bella"

# Silence played before the first word. A Bluetooth speaker's A2DP link takes a
# few hundred milliseconds to wake, and anything sent during that window is
# dropped -- which sounded like the ghost swallowing the start of every
# sentence. Override with GHOST_TTS_LEAD_MS; 0 disables it for a wired output,
# where it is pure added latency.
LEAD_IN_MS = int(os.getenv("GHOST_TTS_LEAD_MS", "1000"))

# ...and a longer one when the speaker has been quiet for a while. Resuming a
# sink that is merely idle takes a few hundred milliseconds; bringing one back
# from deep A2DP suspend takes appreciably longer, which is why 700 ms was
# enough between sentences and still lost the first word after a pause.
LEAD_IN_COLD_MS = int(os.getenv("GHOST_TTS_COLD_LEAD_MS", "2500"))
IDLE_SECONDS = float(os.getenv("GHOST_TTS_IDLE_SECONDS", "20"))

_last_spoken = 0.0


def lead_in_ms() -> int:
    """How much silence to put in front of this utterance."""
    if LEAD_IN_MS <= 0:
        return 0
    if time.monotonic() - _last_spoken > IDLE_SECONDS:
        return max(LEAD_IN_MS, LEAD_IN_COLD_MS)
    return LEAD_IN_MS


def _mark_spoken() -> None:
    global _last_spoken
    _last_spoken = time.monotonic()


# Same shared path speak.py's `audio_lock` uses. A separate copy rather than a
# shared import because that module lives in the voice loop's tree and venv, not
# the ghost's -- but the path is the contract, so both serialise against it.
_AUDIO_LOCK_PATH = "/tmp/dnd-audio.lock"


class _AudioLock:
    """Hold the shared speaker across one whole utterance, blocking others."""

    def __enter__(self):
        import fcntl

        self._fh = open(_AUDIO_LOCK_PATH, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX)
        except OSError:
            pass
        return self

    def __exit__(self, *exc):
        import fcntl

        try:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
        except OSError:
            pass
        self._fh.close()
        return False


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
        """Say it, sentence by sentence, starting as soon as the first is ready.

        Synthesis here runs at about 2.5x realtime, so a four-sentence combat
        result is twenty seconds of silence before a word is heard. Splitting on
        sentences and playing each as it lands cuts the wait to the first
        sentence alone -- measured on this machine, 20.3s to 5.8s.

        Kokoro's own `create_stream` does not help: it only splits at the
        phoneme-length limit, and a whole combat result fits under it, so it
        yields exactly one chunk. The split has to be ours.

        Synthesis runs on a producer thread so sentence N+1 is being made while
        sentence N plays. It cannot fully keep up -- synthesis is slower than
        speech -- so there are still small gaps, but each gap is a fraction of
        the twenty seconds it replaces.

        Playback goes through `pw-play`, not sounddevice, and that is the whole
        point of this function's shape. PortAudio on this Pi has only the ALSA
        host API; the Bluetooth speaker is not an ALSA card, so `sd.OutputStream`
        cannot reach it and quietly plays to HDMI instead. Verified: a six-second
        tone through sounddevice produced no stream in PipeWire at all. The ghost
        narrated to the monitor for a whole session that way.

        One long-lived `pw-play` reading raw floats from stdin, rather than one
        per sentence: a Bluetooth sink suspends the moment its stream closes, so
        per-sentence playback let it doze off between sentences and clip the
        start of every one.
        """
        if not text or not text.strip():
            return
        import queue  # noqa: PLC0415

        sentences = _split_sentences(text)
        if not sentences:
            return

        import numpy as np  # noqa: PLC0415

        with self._lock:
            # Bounded: without a limit a long read-out synthesises the whole
            # thing into memory ahead of playback, which is the behaviour this
            # is meant to avoid.
            clips: queue.Queue = queue.Queue(maxsize=2)

            def produce() -> None:
                for sentence in sentences:
                    try:
                        clips.put(self._kokoro.create(sentence, voice=self.voice, speed=self.speed))
                    except Exception:  # noqa: BLE001
                        log.exception("could not synthesise %r", sentence[:40])
                clips.put(None)

            worker = threading.Thread(target=produce, daemon=True, name="kokoro-synth")
            worker.start()

            first = clips.get()
            if first is None:
                worker.join(timeout=1)
                return
            rate = int(first[1])

            sink = _open_sink(rate)
            self._audio_lock = _AudioLock()
            self._audio_lock.__enter__()
            try:
                # The silence goes in front of the first clip's samples. A
                # separate write races the sink coming up, so the padding is
                # exactly what gets dropped and the speech behind it is clipped
                # anyway; making it part of the audio guarantees that whatever
                # A2DP swallows on wake-up is the quiet part.
                pad = np.zeros(int(rate * lead_in_ms() / 1000), dtype="float32")
                clip = first
                while clip is not None:
                    audio = np.asarray(clip[0], dtype="float32")
                    if pad is not None:
                        audio = np.concatenate([pad, audio])
                        pad = None
                    sink.write(audio)
                    clip = clips.get()
            finally:
                sink.close()
                self._audio_lock.__exit__(None, None, None)
                worker.join(timeout=1)
                _mark_spoken()


class _PwPlaySink:
    """A single `pw-play` process fed raw float32 frames on stdin."""

    def __init__(self, rate: int) -> None:
        env = dict(os.environ)
        # pw-play finds the PipeWire socket through XDG_RUNTIME_DIR, and a ghost
        # started with setsid/nohup from a bare shell does not have one -- it
        # would fail with no output and the ghost would silently stop speaking
        # again, which is the exact bug this file was just fixed for.
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        self.proc = subprocess.Popen(
            [
                "pw-play", "--raw",
                "--format=f32", f"--rate={rate}", "--channels=1",
                "-",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

    def write(self, audio) -> None:
        self.proc.stdin.write(audio.tobytes())
        self.proc.stdin.flush()

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait(timeout=60)


class _SoundDeviceSink:
    """Fallback for a machine with no PipeWire. Cannot reach Bluetooth here."""

    def __init__(self, rate: int) -> None:
        import sounddevice as sd  # noqa: PLC0415

        self.stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32")
        self.stream.start()

    def write(self, audio) -> None:
        self.stream.write(audio)

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()


def _open_sink(rate: int):
    if shutil.which("pw-play") is not None:
        try:
            return _PwPlaySink(rate)
        except Exception:  # noqa: BLE001
            log.exception("pw-play would not start; falling back to sounddevice")
    return _SoundDeviceSink(rate)


# Split on sentence enders, keeping the punctuation. Abbreviations would break
# this, but the input is generated combat prose -- "17 to hit" and "AC 10", not
# "Dr. Smith" -- so the simple rule is the right one here.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]
    # Very short fragments cost a whole synthesis call to say almost nothing, so
    # fold them into the previous sentence.
    merged: list[str] = []
    for part in parts:
        if merged and len(part) < 15:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged
