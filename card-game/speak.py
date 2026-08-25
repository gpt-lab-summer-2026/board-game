import re
import sounddevice as sd
from concurrent.futures import ThreadPoolExecutor
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


def split_sentences(text):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if s]


def speak(text, voice=VOICE, speed=SPEED):
    if not text or not text.strip():
        return
    sentences = split_sentences(text)
    if not sentences:
        return

    engine = get_engine()

    def synth(sentence):
        return engine.create(sentence, voice=voice, speed=speed)

    # Synthesize the next sentence while the current one plays, so playback
    # of sentence N overlaps with TTS generation of sentence N+1.
    with ThreadPoolExecutor(max_workers=1) as executor:
        next_future = executor.submit(synth, sentences[0])
        for i in range(len(sentences)):
            samples, sample_rate = next_future.result()
            if i + 1 < len(sentences):
                next_future = executor.submit(synth, sentences[i + 1])
            # Blocking: two narrations talking over each other is worse than a pause.
            sd.play(samples, sample_rate)
            sd.wait()