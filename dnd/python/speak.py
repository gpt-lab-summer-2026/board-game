import os
import subprocess
import tempfile

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from kokoro_onnx import Kokoro

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, "..", "..", "models", "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

VOICE = "bf_lily"
SPEED = 1.0
PLAYER = "pw-play"

_kokoro = None


def get_engine():
    global _kokoro
    if _kokoro is None:
        _kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
    return _kokoro


def warm_up(voice=VOICE, speed=SPEED):
    get_engine().create("ready", voice=voice, speed=speed)


def play(samples, sample_rate):
    audio = (np.clip(samples, -1.0, 1.0) * 32767).astype("int16")
    tmp_path = os.path.join(tempfile.gettempdir(), f"kokoro-{os.getpid()}.wav")
    try:
        write(tmp_path, sample_rate, audio)
        # Blocking: two narrations talking over each other is worse than a pause.
        subprocess.run([PLAYER, tmp_path], check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        # Fall back rather than lose the line; on HDMI it is at least audible.
        print(f"{PLAYER} playback failed ({e}), falling back to sounddevice")
        sd.play(samples, sample_rate)
        sd.wait()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def speak(text, voice=VOICE, speed=SPEED):
    if not text or not text.strip():
        return
    samples, sample_rate = get_engine().create(text, voice=voice, speed=speed)
    play(samples, sample_rate)


if __name__ == "__main__":
    speak("The goblin swings wide and the blade bites into the elf's shoulder.")
