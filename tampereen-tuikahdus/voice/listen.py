from __future__ import annotations

import json
import logging
import queue
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import gcd
from urllib.parse import urlsplit

import numpy as np
import sounddevice as sd
import websockets
from websockets.sync.server import serve as ws_serve

from .config import AudioConfig, SttConfig, VadConfig, WakeWordConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Microphone capture
# ---------------------------------------------------------------------------
# sounddevice keeps one real PortAudio stream open for the entire run, fed by
# a callback into a queue -- not a subprocess spawned per phase. That's what
# makes wake-word detection and command recording share the same live audio
# with no gap between them: there's no process to spin up or tear down at the
# handoff, just the next block already sitting in the queue.

class AudioCapture:
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        self._queue: queue.Queue = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=cfg.capture_rate,
            channels=cfg.channels,
            dtype="int16",
            device=cfg.input_device,
            blocksize=cfg.capture_rate // 10,  # 100ms blocks; large enough to survive a stall
            latency="high",
            callback=self._on_audio,
        )
        self._stream.start()
        log.info("Capturing via sounddevice (device=%r, %d Hz -> %d Hz)",
                  cfg.input_device, cfg.capture_rate, cfg.sample_rate)

    def _on_audio(self, indata, _frames, _time_info, status) -> None:
        # "input overflow" here means PortAudio dropped blocks because nothing drained
        # the queue in time -- keep this callback trivial, all analysis belongs in the
        # polling loops below, not in the audio thread.
        if status:
            log.warning("audio input status: %s", status)
        self._queue.put(indata.copy().reshape(-1))

    def drain_native(self) -> np.ndarray:
        """Everything captured since the last drain, at cfg.capture_rate, int16."""
        blocks = []
        while True:
            try:
                blocks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not blocks:
            return np.zeros(0, dtype="int16")
        return np.concatenate(blocks)

    def drain(self) -> np.ndarray:
        """Everything captured since the last drain, resampled to cfg.sample_rate,
        float32 in [-1, 1] -- what openWakeWord, silero-vad and whisper all want."""
        native = self.drain_native().astype("float32") / 32768.0
        if len(native) == 0:
            return native
        return resample(native, self.cfg.capture_rate, self.cfg.sample_rate)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Polyphase-resample mono float32 audio (e.g. mic's 48 kHz -> Whisper's 16 kHz)."""
    if orig_sr == target_sr:
        return samples
    from scipy.signal import resample_poly  # lazy: only needed when rates actually differ

    g = gcd(orig_sr, target_sr)
    up, down = target_sr // g, orig_sr // g   # 48000 -> 16000 reduces to up=1, down=3
    return resample_poly(samples, up, down).astype("float32")


def to_int16(samples: np.ndarray) -> np.ndarray:
    return (np.clip(samples, -1.0, 1.0) * 32767).astype("int16")


def save_wav(path: str, samples: np.ndarray, sample_rate: int) -> None:
    """Write float32 [-1, 1] mono samples as 16-bit PCM, stdlib-only (no soundfile dependency)."""
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(to_int16(samples).tobytes())


class RollingWindow:
    """A rolling view of resampled 16 kHz audio, trimmed to the last
    `window_seconds` so re-scoring cost per poll stays constant instead of
    growing with how long a turn has been going. Sample counts (start/elapsed)
    stay absolute across trims via `trimmed`, so a caller can compare VAD
    timestamps across polls even after old audio has scrolled out of the window.
    Pass keep_all=True to also retain the complete, untrimmed history (e.g. for
    the final transcription, which needs everything, not just the recent tail).
    """

    def __init__(self, sample_rate: int, window_seconds: float, keep_all: bool = False):
        self.sample_rate = sample_rate
        self.max_samples = int(window_seconds * sample_rate)
        self.audio = np.zeros(0, dtype="float32")
        self.trimmed = 0
        self.all_audio = np.zeros(0, dtype="float32") if keep_all else None

    def add(self, fresh: np.ndarray) -> None:
        if len(fresh) == 0:
            return
        if self.all_audio is not None:
            self.all_audio = np.concatenate((self.all_audio, fresh))
        self.audio = np.concatenate((self.audio, fresh))
        excess = len(self.audio) - self.max_samples
        if excess > 0:
            self.audio = self.audio[excess:]
            self.trimmed += excess

    @property
    def start(self) -> float:
        """Seconds from the beginning of the window's life to the start of its current view."""
        return self.trimmed / self.sample_rate

    @property
    def elapsed(self) -> float:
        return (self.trimmed + len(self.audio)) / self.sample_rate


# ---------------------------------------------------------------------------
# Wake-word detection
# ---------------------------------------------------------------------------
# openWakeWord runs continuously on streamed mic audio, cheaply (tiny ONNX
# models, single thread), so the Pi can sit listening all game without
# transcribing anything until a player actually says the wake word.

CHUNK_SAMPLES = 1280  # openWakeWord's native frame size: 80ms at 16 kHz


class WakeWordEvent:
    def __init__(self, model: str, score: float):
        self.model = model
        self.score = score


class WakeWordDetector:
    def __init__(self, cfg: WakeWordConfig):
        import warnings

        import openwakeword
        from openwakeword.model import Model

        # openwakeword asks onnxruntime for CUDAExecutionProvider first and falls back to
        # CPU -- harmless on a GPU-less Pi, but noisy every time a session is created.
        warnings.filterwarnings("ignore", message=r"Specified provider 'CUDAExecutionProvider'",
                                 category=UserWarning)

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
            # name resolves to a real file.
            raise RuntimeError(
                "Couldn't load the wake word model -- if this is a fresh install, fetch the "
                "bundled model weights once with: python -c "
                "\"from openwakeword.utils import download_models; download_models()\". "
                f"Original error: {e}"
            ) from e
        self._model_name = next(iter(self._model.models))
        self._armed = True  # fires once per rise above threshold, not once per frame while held
        self.last_score = 0.0  # updated on every process_chunk call
        self._pending = np.zeros(0, dtype="int16")  # feed()'s leftover, not yet a full frame

    def process_chunk(self, chunk: np.ndarray) -> WakeWordEvent | None:
        """chunk: exactly CHUNK_SAMPLES int16 samples at 16 kHz."""
        score = float(self._model.predict(chunk)[self._model_name])
        self.last_score = score
        detected = score >= self.cfg.threshold
        fire = detected and self._armed
        self._armed = not detected
        return WakeWordEvent(self._model_name, score) if fire else None

    def feed(self, audio: np.ndarray) -> WakeWordEvent | None:
        """audio: float32 [-1, 1] at 16 kHz, any length -- buffers into fixed-size
        frames internally so callers can just hand over whatever a drain() returned."""
        self._pending = np.concatenate((self._pending, to_int16(audio)))
        while len(self._pending) >= CHUNK_SAMPLES:
            frame, self._pending = self._pending[:CHUNK_SAMPLES], self._pending[CHUNK_SAMPLES:]
            event = self.process_chunk(frame)
            if event is not None:
                return event
        return None


def wait_for_wake_word(capture: AudioCapture, detector: WakeWordDetector,
                        poll_seconds: float = 0.1) -> None:
    while True:
        if detector.feed(capture.drain()) is not None:
            return
        sd.sleep(int(poll_seconds * 1000))


# ---------------------------------------------------------------------------
# Voice activity detection -- decides when a command recording ends
# ---------------------------------------------------------------------------

class VoiceActivityDetector:
    def __init__(self):
        from silero_vad import load_silero_vad  # lazy: heavy dependency (torch)

        self._model = load_silero_vad()

    def speech_timestamps(self, audio: np.ndarray, sample_rate: int,
                           threshold: float) -> list[dict]:
        """Speech (start, end) timestamps in seconds for float32 mono audio in memory."""
        import torch
        from silero_vad import get_speech_timestamps

        if len(audio) < 512:
            return []
        return get_speech_timestamps(
            torch.from_numpy(np.ascontiguousarray(audio)),
            self._model, threshold=threshold, sampling_rate=sample_rate,
            return_seconds=True,
        )


def record_until_silence(capture: AudioCapture, vad: VoiceActivityDetector,
                          cfg: VadConfig, sample_rate: int = 16000) -> np.ndarray:
    """Record from right after the wake word until the player actually stops
    talking -- ending on `cfg.silence_stop_seconds` of trailing silence, not a
    fixed duration, so a one-word "roll" and a full sentence both feel natural
    instead of the mic always waiting out the same fixed window either way.

    Returns an empty array if nothing is said within cfg.wait_seconds.
    """
    window = RollingWindow(sample_rate, cfg.analysis_window_seconds, keep_all=True)
    heard_speech = False
    last_speech_end = 0.0
    while True:
        sd.sleep(int(cfg.poll_seconds * 1000))
        window.add(capture.drain())
        timestamps = vad.speech_timestamps(window.audio, sample_rate, cfg.threshold)
        if timestamps:
            heard_speech = True
            last_speech_end = window.start + timestamps[-1]["end"]
        if heard_speech:
            if window.elapsed - last_speech_end >= cfg.silence_stop_seconds:
                break
            if window.elapsed >= cfg.max_seconds:
                log.info("command ran long, cutting off at %.0fs", cfg.max_seconds)
                break
        elif window.elapsed >= cfg.wait_seconds:
            log.info("nothing said after the wake word")
            return np.zeros(0, dtype="float32")
    return window.all_audio


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------

class CommandTranscriber:
    def __init__(self, cfg: SttConfig):
        from faster_whisper import WhisperModel  # lazy: heavy dependency

        self.cfg = cfg
        log.info("Loading whisper model %s (%s/%s)...", cfg.model, cfg.device, cfg.compute_type)
        self._model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)

    def transcribe(self, audio: np.ndarray, vad_filter: bool = True) -> str:
        segments, _info = self._model.transcribe(audio, language=self.cfg.language, beam_size=5,
                                                   vad_filter=vad_filter,
                                                   initial_prompt=self.cfg.initial_prompt)
        return " ".join(seg.text.strip() for seg in segments).strip()


class UiServer:
    def __init__(self, port: int = 8765, ws_port: int = 8766):
        self._lock = threading.Lock()
        self._message = "Waiting for a player to speak..."
        self._event: dict | None = None
        self._current_player: str | None = None
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

        self._ws_clients: set = set()
        self._ws_lock = threading.Lock()
        self._wsd = ws_serve(self._handle_ws, "0.0.0.0", ws_port)
        self._ws_thread = threading.Thread(target=self._wsd.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ws_thread.start()
        log.info("Status server listening on http://0.0.0.0:%d/status", self._httpd.server_port)
        log.info("Transcript websocket listening on ws://0.0.0.0:%d", self._wsd.socket.getsockname()[1])

    def set_message(self, text: str, event: dict | None = None) -> None:
        with self._lock:
            self._message = text
            self._event = event

    def get_status(self) -> dict:
        with self._lock:
            return {"message": self._message, "event": self._event}

    def broadcast_transcript(self, player: str, text: str, phase: str = "playing",
                              event: str | None = None) -> None:
        self._broadcast({"kind": "transcript", "player": player, "text": text,
                          "phase": phase, "event": event})

    def broadcast_status(self, status: str, player: str | None = None) -> None:
        self._broadcast({"kind": "status", "status": status, "player": player})

    def _broadcast(self, payload: dict) -> None:
        encoded = json.dumps(payload)
        with self._ws_lock:
            clients = list(self._ws_clients)
        for client in clients:
            try:
                client.send(encoded)
            except websockets.exceptions.ConnectionClosed:
                pass  # _handle_ws's own finally block discards it from _ws_clients

    def get_current_player(self) -> str | None:
        with self._lock:
            return self._current_player

    def _handle_ws(self, client) -> None:
        with self._ws_lock:
            self._ws_clients.add(client)
            other_clients = len(self._ws_clients) - 1
        if other_clients > 0:
            # Each browser tab runs a fully independent copy of the game (no
            # shared/backend game state at all) -- if more than one is open,
            # whichever last reports current_player silently overwrites the
            # other's, with no way to tell from here which one you actually
            # meant to use. This can't be resolved automatically; it's meant
            # to make that failure mode loud instead of a silent mystery bug.
            log.warning("Another %d browser tab(s) already connected -- if you have more "
                        "than one tab/window open on this app, close the old ones, or "
                        "they'll fight over whose turn it is.", other_clients)
        try:
            for raw in client:
                self._handle_ws_message(raw)
        except websockets.exceptions.ConnectionClosed:
            pass  # a closed tab/dropped connection is routine, not an error to log
        finally:
            with self._ws_lock:
                self._ws_clients.discard(client)

    def _handle_ws_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Ignoring malformed websocket message: %r", raw)
            return
        if msg.get("type") == "current_player":
            player = msg.get("player")
            with self._lock:
                self._current_player = player
            log.info("Browser reports current player: %s", player)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._wsd.shutdown()


def _build_handler(server: UiServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # route stdlib's request logging through ours
            log.debug(fmt, *args)

        def do_GET(self):
            # Split off any query string: a polling client cache-busting with
            # /status?t=123 was previously falling through to a 404.
            if urlsplit(self.path).path != "/status":
                self.send_error(404)
                return
            body = json.dumps(server.get_status()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # The board UI is served by Vite on another port, so it needs this.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

    return Handler
