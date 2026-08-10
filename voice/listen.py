from __future__ import annotations

import json
import logging
import shutil
import signal
import subprocess
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import gcd
from urllib.parse import urlsplit

import numpy as np
import websockets
from websockets.sync.server import serve as ws_serve

from .config import AudioConfig, SttConfig, WakeWordConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Microphone capture
# ---------------------------------------------------------------------------

class AudioCapture:
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
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
        self.last_score = 0.0  # updated on every process_chunk call -- see test_wakeword.py

    def process_chunk(self, chunk: np.ndarray) -> WakeWordEvent | None:
        score = float(self._model.predict(chunk)[self._model_name])
        self.last_score = score
        detected = score >= self.cfg.threshold
        fire = detected and self._armed
        self._armed = not detected
        return WakeWordEvent(self._model_name, score) if fire else None


def wait_for_wake_word(capture: AudioCapture, detector: WakeWordDetector, rolling) -> np.ndarray:

    for chunk in capture.stream_16k_chunks(CHUNK_SAMPLES):
        rolling.append(chunk)
        event = detector.process_chunk(chunk)
        if event is None:
            continue
        return np.concatenate(list(rolling))


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
