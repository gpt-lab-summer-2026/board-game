"""Text to speech via Kokoro.

`streaming-tts` pulls in the torch build of kokoro, which caps at Python 3.12
and drags spacy/transformers/CUDA along with it. This machine is on 3.13, so we
use `kokoro-onnx` against the ONNX weights instead — same voices, onnxruntime
only, and it is what already ran on this Pi.

The model is 325 MB, so it is loaded on the first call rather than at import:
`listen.py` imports this module too and should not pay for the model unless
something actually speaks.
"""
import os
import sounddevice as sd
from kokoro_onnx import Kokoro

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, "..", "..", "models", "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

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


if __name__ == "__main__":
    speak("The goblin swings wide and the blade bites into the elf's shoulder.")
