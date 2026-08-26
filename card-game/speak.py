import sounddevice as sd
from kokoro_onnx import Kokoro

MODEL_PATH = "../models/kokoro-v1.0.onnx"
VOICES_PATH = "voices/voices-v1.0.bin"

VOICE = "bf_lily"
SPEED = 1.0

_kokoro = None

def get_engine():
    global _kokoro
    if _kokoro is None:
        _kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
    return _kokoro


def speak(text, voice=VOICE, speed=SPEED):
    if not text or not text.strip():
        return
    samples, sample_rate = get_engine().create(text, voice=voice, speed=speed)
    # Blocking: two narrations talking over each other is worse than a pause.
    sd.play(samples, sample_rate)
    sd.wait()