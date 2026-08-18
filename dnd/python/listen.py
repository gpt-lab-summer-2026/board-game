import os
import queue
import sys
import openwakeword
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
import torch
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from math import gcd
from silero_vad import load_silero_vad, get_speech_timestamps
from openwakeword.model import Model

from speak import *
from ghost_client import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import HELP_TEXT

#openwakeword.utils.download_models() # run this once when first time running the program

AUDIO_DEVICE = 2 # check correct device with 'python -m sounddevice'
FS = 48000
TARGET_FS = 16000  # what silero, openwakeword and whisper all want
REC_PATH = os.path.join(SCRIPT_DIR, "recordings", "listen.wav")
BLOCK_SIZE = 4800  # 100 ms at 48 kHz; large blocks survive main-thread stalls
POLL_INTERVAL_MS = 500  # how often each listening loop checks the accumulated audio so far
WAKE_WORD = "hey_jarvis"
FRAME_SIZE = 1280  # openwakeword wants 80 ms int16 frames at 16 kHz
VAD_THRESHOLD = 0.5  # min speech probability (0-1); raise to ignore background noise
SILENCE_STOP_SECONDS = 1.2  # trailing silence needed to end the turn
ANALYSIS_WINDOW_SECONDS = 3.0  # only this much tail audio is re-analysed per poll
COMMAND_WAIT_SECONDS = 10.0  # give up if nothing is said after the wake word
MAX_COMMAND_SECONDS = 30.0  # hard cap so a stuck VAD cannot record forever

MODEL = WhisperModel("distil-small.en", device="cpu", compute_type="int8")
VADMODEL = load_silero_vad()
# Loading only the one wake word instead of all five pretrained models cuts the
# per-frame inference cost by ~5x. Loading by path names the model after the
# file, so ask the model object what it ended up calling it.
WAKEWORD_MODEL = Model(wakeword_model_paths=[openwakeword.models[WAKE_WORD]["model_path"]])
WAKEWORD_KEY = next(iter(WAKEWORD_MODEL.models))

AUDIO_QUEUE = queue.Queue()

CURRENT_CHARACTERS = []

def callback(indata, frames, time, status):
    # "input overflow" here means PortAudio threw away captured blocks because
    # nothing drained them in time, so the recording has a gap. Keep this
    # callback trivial -- all analysis belongs in the polling loops below.
    if status:
        print("audio input status: ", status)
    AUDIO_QUEUE.put(indata.copy().squeeze())

def drain_queue():
    """Throw away whatever the callback has buffered so far."""
    while True:
        try:
            AUDIO_QUEUE.get_nowait()
        except queue.Empty:
            return

def resample(audio, orig_rate=FS, target_rate=TARGET_FS):
    """int16 at orig_rate -> float32 in [-1, 1] at target_rate."""
    g = gcd(orig_rate, target_rate)
    up, down = target_rate // g, orig_rate // g
    return resample_poly(audio.astype(np.float32) / 32768.0, up, down).astype(np.float32)

def to_int16(audio):
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("int16")

def write_recording(audio, path=REC_PATH, rate=TARGET_FS):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write(path, rate, to_int16(audio))

class AudioWindow:
    """A rolling 16 kHz view of the input stream.

    Each captured block is resampled exactly once and only the last
    ANALYSIS_WINDOW_SECONDS are kept, so the cost of a poll stays constant
    instead of growing with how long we have been listening. Timestamps stay
    absolute (seconds since the window was created) via `start`, so callers can
    compare them across polls even after audio has scrolled out.
    """

    def __init__(self, keep_raw=False, window_seconds=ANALYSIS_WINDOW_SECONDS):
        self.max_samples = int(window_seconds * TARGET_FS)
        self.audio = np.zeros(0, dtype=np.float32)
        self.trimmed = 0  # 16 kHz samples dropped off the front of the window
        self.keep_raw = keep_raw
        self.raw = []

    def drain(self):
        """Pull everything the callback has queued. Returns the new 16 kHz audio."""
        blocks = []
        while True:
            try:
                blocks.append(AUDIO_QUEUE.get_nowait())
            except queue.Empty:
                break
        if not blocks:
            return np.zeros(0, dtype=np.float32)
        raw = np.concatenate(blocks)
        if self.keep_raw:
            self.raw.append(raw)
        fresh = resample(raw)
        self.audio = np.concatenate((self.audio, fresh))
        excess = len(self.audio) - self.max_samples
        if excess > 0:
            self.audio = self.audio[excess:]
            self.trimmed += excess
        return fresh

    @property
    def start(self):
        """Seconds from the beginning of the stream to the start of the window."""
        return self.trimmed / TARGET_FS

    @property
    def elapsed(self):
        return (self.trimmed + len(self.audio)) / TARGET_FS

    def full_audio(self):
        """Everything captured, at the original rate. Empty unless keep_raw."""
        if not self.raw:
            return np.zeros(0, dtype="int16")
        return np.concatenate(self.raw)

class WakeWordListener:
    """Feeds the stream to openwakeword one frame at a time, exactly once.

    The model carries internal feature state and expects a continuous stream.
    Re-running it over the whole buffer on every poll -- as the VAD-gated
    version did -- both burned CPU quadratically and fed it overlapping audio.
    """

    def __init__(self, threshold=0.5):
        self.threshold = threshold
        self.pending = np.zeros(0, dtype="int16")
        WAKEWORD_MODEL.reset()

    def feed(self, audio):
        """audio: float32 16 kHz. True once the wake word fires."""
        if len(audio) == 0:
            return False
        self.pending = np.concatenate((self.pending, to_int16(audio)))
        while len(self.pending) >= FRAME_SIZE:
            frame = self.pending[:FRAME_SIZE]
            self.pending = self.pending[FRAME_SIZE:]
            if WAKEWORD_MODEL.predict(frame)[WAKEWORD_KEY] > self.threshold:
                return True
        return False

def vad(audio, threshold=VAD_THRESHOLD):
    """Speech timestamps (in seconds) for float32 16 kHz audio held in memory."""
    if len(audio) < 512:
        return []
    return get_speech_timestamps(
        torch.from_numpy(np.ascontiguousarray(audio)),
        VADMODEL,
        threshold=threshold,
        sampling_rate=TARGET_FS,
        return_seconds=True,  # Return speech timestamps in seconds (default is samples)
    )

def record_audio():
    """Wait for the wake word, then capture the command that follows.

    Returns the raw command audio at FS, and writes the 16 kHz wav that
    transcribe() reads. An empty array means nothing usable was captured.
    """
    try:
        with sd.InputStream(
            samplerate=FS,
            channels=1,
            dtype="int16",
            device=AUDIO_DEVICE,
            blocksize=BLOCK_SIZE,
            latency="high",
            callback=callback,
        ):
            drain_queue()
            print("listening for wake word")
            window = AudioWindow()
            detector = WakeWordListener()
            while not detector.feed(window.drain()):
                sd.sleep(POLL_INTERVAL_MS)
            print("wake word detected!")
            speak("how can i help?")

            # Everything recorded while waiting -- including our own prompt
            # coming back through the mic -- is not part of the command.
            drain_queue()
            window = AudioWindow(keep_raw=True)
            heard_speech = False
            last_speech_end = 0.0
            while True:
                sd.sleep(POLL_INTERVAL_MS)
                window.drain()
                speech_timestamps = vad(window.audio)
                if speech_timestamps:
                    heard_speech = True
                    last_speech_end = window.start + speech_timestamps[-1]["end"]
                if heard_speech:
                    if window.elapsed - last_speech_end >= SILENCE_STOP_SECONDS:
                        break
                    if window.elapsed >= MAX_COMMAND_SECONDS:
                        print("command ran long, cutting off")
                        break
                elif window.elapsed >= COMMAND_WAIT_SECONDS:
                    print("nothing said after the wake word")
                    return np.zeros(0, dtype="int16")
            raw = window.full_audio()
    except Exception as e:
        print("recording failed: ", e)
        return np.zeros(0, dtype="int16")

    if len(raw) == 0:
        return raw
    write_recording(resample(raw))
    return raw

def build_initial_prompt():
    roster = ", ".join(CURRENT_CHARACTERS) if CURRENT_CHARACTERS else ""
    return (
        f"The party is {roster}. "
        "Commands: melee attack, ranged attack, cantrip, move, walk, approach, "
        "measure distance, duplicate, apply prone, apply poisoned, apply stunned, "
        "clear condition, advantage, disadvantage, yes, no, help."
    )

def transcribe():
    # transcribe the audio currently written to REC_PATH
    print("transcribing")
    segments, _ = MODEL.transcribe(
        REC_PATH,
        condition_on_previous_text=False,
        language="en",
        vad_filter=True,
        #initial_prompt=build_initial_prompt(), # prompt kinda brakes whisper, TODO fix this
    )
    text = "".join(segment.text for segment in segments).strip().rstrip(".!?,;:")
    return text

def listen_user():
    global CURRENT_CHARACTERS
    CURRENT_CHARACTERS = getReq()

    # Without this guard a failed recording would transcribe whatever wav was
    # left over from the previous turn.
    if len(record_audio()) == 0:
        return ""
    text = transcribe()
    print("transcribed text: ", text)
    return text
