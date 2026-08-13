import openwakeword
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
from faster_whisper import WhisperModel

from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
from openwakeword.model import Model
from speak import *

# openwakeword.utils.download_models() # run this once when first time running the program

MODEL = WhisperModel("small", device="cpu", compute_type="int8")
VADMODEL = load_silero_vad()
WAKEWORD_MODEL = Model(inference_framework="onnx")

AUDIO_DEVICE = 1 # check correct device with 'python -m sounddevice'
FS = 48000
REC_PATH = "recordings/listen.wav"
DURATION = 3
AUDIO_DATA = []
WAKE_WORD = "hey_jarvis"
FRAME_SIZE = 1280
VAD_THRESHOLD = 0.5  # min speech probability (0-1); raise to ignore background noise

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

def record_audio(duration):
    global AUDIO_DATA
    AUDIO_DATA = []
    try:
        with sd.InputStream(samplerate=FS, channels=1, dtype="int16", device=AUDIO_DEVICE, callback=callback):
            print("listening")
            sd.sleep(int(duration * 1000))

    except Exception as e:
        print("recording failed: ", e)

    if not AUDIO_DATA:
        return np.array([], dtype="int16")
    return np.concatenate(AUDIO_DATA)

def resample(audio, target_rate=16000):
    # resample to 16k
    print("resampling")
    audio_f = np.asarray(audio).flatten()
    new_len = int(len(audio_f) * target_rate / FS)
    old_idx = np.linspace(0, len(audio_f) - 1, new_len)
    audio_float32 = audio_f.astype(np.float32, order='C') / 32767
    audio16k = np.interp(old_idx, np.arange(len(audio_float32)), audio_float32)
    audio16k_int16 = (audio16k * 32767).astype(np.int16)

    write(REC_PATH, target_rate, audio16k_int16) # numpy to wav
    return audio16k_int16

def transcribe():
    # transcribe the audio currently written to REC_PATH
    print("transcribing")
    segments, _ = MODEL.transcribe(
        REC_PATH,
        condition_on_previous_text=False,
        temperature=0.0,
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

    noWakeWord = True
    while noWakeWord:
        recorded = record_audio(duration=DURATION)
        audio = resample(audio=recorded)
        # get timestamps when speech detected
        speech_timestamps = vad()
        if speech_timestamps:
            print("timestamps: ", speech_timestamps)
            if detect_wake_word(audio=audio, timestamps=speech_timestamps):
                print("wake word detected!")
                speak("how can i help?")
                noWakeWord = False
    # wake word has been detected
    speech = True
    whole_audio = []
    while speech:
        recorded = record_audio(duration=5)
        audio = resample(audio=recorded)
        whole_audio.append(audio)

        # get timestamps when speech detected
        speech_timestamps = vad()
        if not speech_timestamps:
            speech = False

    # write the full utterance (all chunks) as one file and transcribe that
    final_audio = np.concatenate(whole_audio)
    write(REC_PATH, 16000, final_audio)
    text = transcribe()
    print("transcribed text: ", text)
    return text
