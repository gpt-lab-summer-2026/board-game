import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
from faster_whisper import WhisperModel
from streaming_tts import TextToAudioStream, KokoroEngine

MODEL = WhisperModel("small", device="cpu", compute_type="int8")

AUDIO_DEVICE = 1 # check correct device
FS = 48000
REC_PATH = "recordings/rec.wav"
DURATION = 5
AUDIO_DATA = []

def callback(indata, frames, time, status):
    if status:
        print("error is callback: ", status)
    AUDIO_DATA.append(indata.copy().squeeze())

def record_audio():
    try:
        with sd.InputStream(samplerate=FS, channels=1, dtype="int16", device=AUDIO_DEVICE, callback=callback):
            print("listening")
            sd.sleep(int(DURATION * 1000))
            
    except Exception as e:
        print("recording failed: ", e)

def transcribe(audio, target_rate=16000):
    # resample to 16k
    print("resampling")
    audio_f = np.asarray(audio).flatten()
    new_len = int(len(audio_f) * target_rate / FS)
    old_idx = np.linspace(0, len(audio_f) - 1, new_len)
    audio_float32 = audio_f.astype(np.float32, order='C') / 32767
    audio16k = np.interp(old_idx, np.arange(len(audio_float32)), audio_float32)
    audio16k_int16 = (audio16k * 32767).astype(np.int16)

    write("recordings/listen.wav", target_rate, audio16k_int16) # numpy to wav

    # transcribe
    print("transcribing")
    segments, _ = MODEL.transcribe(
        "recordings/listen.wav",
        condition_on_previous_text=False,
        temperature=0.0,
    )
    text = "".join(segment.text for segment in segments).strip().rstrip(".!?,;:")
    return text

def listen_user():
    record_audio()
    return transcribe(audio=AUDIO_DATA)

def speak(text):
    # Initialize the engine
    engine = KokoroEngine(voice="bf_lily")
        
    # Create stream and play
    stream = TextToAudioStream(engine)
    stream.feed(text).play()
    
    # Process text with pauses
    # for item in process_text_with_pauses(text, normalize=True):
    #     if isinstance(item, float):
    #         time.sleep(item)  # Pause
    #     else:
    #         stream.feed(item).play()  # Speak