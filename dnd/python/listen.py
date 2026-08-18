import os
import sys
import openwakeword
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from math import gcd
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
from openwakeword.model import Model

from speak import *
from ghost_client import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import HELP_TEXT

#openwakeword.utils.download_models() # run this once when first time running the program

MODEL = WhisperModel("distil-small.en", device="cpu", compute_type="int8")
VADMODEL = load_silero_vad()
WAKEWORD_MODEL = Model()

AUDIO_DEVICE = 2 # check correct device with 'python -m sounddevice'
FS = 48000
REC_PATH = "recordings/listen.wav"
POLL_INTERVAL_MS = 500  # how often each listening loop checks the accumulated audio so far
AUDIO_DATA = []
WAKE_WORD = "hey_jarvis"
FRAME_SIZE = 1280
VAD_THRESHOLD = 0.5  # min speech probability (0-1); raise to ignore background noise
SILENCE_STOP_SECONDS = 1.2  # trailing silence needed to end the turn

CURRENT_CHARACTERS = []

def vad(threshold=VAD_THRESHOLD):
    wav = read_audio(REC_PATH)
    return get_speech_timestamps(
        wav,
        VADMODEL,
        threshold=threshold,
        return_seconds=True,  # Return speech timestamps in seconds (default is samples)
    )

def callback(indata, frames, time, status):
    if status:
        print("error is callback: ", status)
    AUDIO_DATA.append(indata.copy().squeeze())

def record_audio():
    global AUDIO_DATA
    AUDIO_DATA = []
    try:
        with sd.InputStream(samplerate=FS, channels=1, dtype="int16", device=AUDIO_DEVICE, callback=callback):
            print("listening for wake word")
            noWakeWord = True
            while noWakeWord:
                sd.sleep(POLL_INTERVAL_MS)
                if not AUDIO_DATA:
                    continue
                audio = resample(audio=np.concatenate(AUDIO_DATA))
                # get timestamps when speech detected
                speech_timestamps = vad()
                if speech_timestamps:
                    print("timestamps: ", speech_timestamps)
                    if detect_wake_word(audio=audio, timestamps=speech_timestamps):
                        print("wake word detected!")
                        speak("how can i help?")
                        noWakeWord = False

            # wake word has been detected -- start capturing only the command itself,
            # not everything recorded while waiting
            AUDIO_DATA = []
            speech = True
            heard_speech = False
            last_speech_end=0.0
            while speech:
                print("listening speech")
                print("speech: ", speech)
                sd.sleep(POLL_INTERVAL_MS)
                if not AUDIO_DATA:
                    continue
                audio_16k = resample(audio=np.concatenate(AUDIO_DATA))
                # get timestamps when speech detected
                speech_timestamps = vad()
                print(speech_timestamps)
                if speech_timestamps:
                    heard_speech = True
                    last_speech_end = speech_timestamps[-1]["end"]
                if heard_speech:
                    print("putting speech false")
                    buffer_seconds = len(audio_16k) / 16000
                    if buffer_seconds - last_speech_end >= SILENCE_STOP_SECONDS:
                        speech = False
                
    except Exception as e:
        print("recording failed: ", e)

    if not AUDIO_DATA:
        return np.array([], dtype="int16")
    return np.concatenate(AUDIO_DATA)

def resample(audio, target_rate=16000):
    # resample to 16k
    print("resampling")
    
    g = gcd(FS, target_rate)
    up, down = target_rate // g, FS // g
    audio_norm = audio.astype(np.float32) / 32768.0
    audio_float32 = resample_poly(audio_norm, up, down)
    audio16k_int16 = (np.clip(audio_float32, -1.0, 1.0) * 32767).astype("int16")

    write(REC_PATH, target_rate, audio16k_int16) # numpy to wav
    return audio16k_int16

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

def detect_wake_word(audio, timestamps, wake_word=WAKE_WORD):
    for ts in timestamps:
        start_sample = int(ts["start"] * 16000)
        end_sample = int(ts["end"] * 16000)
        speech = audio[start_sample:end_sample]

        for start in range(0, len(speech) - FRAME_SIZE + 1, FRAME_SIZE):
            frame = speech[start:start + FRAME_SIZE]
            prediction = WAKEWORD_MODEL.predict(frame)
            if prediction[wake_word] > 0.5:
                return True
    return False

def listen_user():
    global CURRENT_CHARACTERS
    CURRENT_CHARACTERS = getReq()

    record_audio()
    text = transcribe()
    print("transcribed text: ", text)
    return text
