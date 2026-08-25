import os
import subprocess
import time
import tempfile

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from kokoro_onnx import Kokoro

from ghost_client import audio_lock, speak_remote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, "..", "..", "models", "kokoro")
MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

# af_heart, not bf_lily. Kokoro grades its voices, and bf_lily is one of the
# weakest in the pack while af_heart is the strongest -- that difference is most
# of what "sounds robotic" was. It also matches the voice the ghost narrates in,
# so the table hears one speaker rather than two. Override with KOKORO_VOICE.
VOICE = os.getenv("KOKORO_VOICE", "af_bella")
SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))
PLAYER = "pw-play"
# Silence written in front of every clip. A Bluetooth sink is suspended between
# lines, and the few hundred milliseconds it takes A2DP to wake are simply
# dropped -- which sounds like the first word being bitten off. Padding the WAV
# itself means whatever gets swallowed is guaranteed to be the quiet part.
# Set LEAD_IN_MS=0 for a wired output, where it is pure added latency.
LEAD_IN_MS = int(os.getenv("LEAD_IN_MS", 400))
# ...and more when the speaker has been quiet for a while. Resuming a sink that
# is merely idle takes a few hundred milliseconds; bringing one back from deep
# A2DP suspend takes appreciably longer. That is why 700 ms was enough between
# lines of a result and still lost the front of "how can i help?", which is
# always the first thing said after a silence.
COLD_LEAD_IN_MS = int(os.getenv("COLD_LEAD_IN_MS", 700))
IDLE_SECONDS = float(os.getenv("SPEAKER_IDLE_SECONDS", 20))

_last_played = 0.0

# --- Bluetooth keep-alive ----------------------------------------------------
#
# The real cause of the clipped first word: an A2DP sink suspends when no audio
# flows, and waking it drops whatever is playing at that instant -- so leading
# silence in the file does not help, because the link wakes *into* the file and
# eats real samples once the padding is exhausted. The fix is to never let it
# sleep. One always-on stream of true silence keeps the link warm; PipeWire
# mixes it under real speech, so it is inaudible and needs no lock. With this
# running, playback starts on an already-awake sink and nothing is bitten off.
#
# Set SPEAKER_KEEPALIVE=0 for a wired output, where nothing sleeps and this is
# pure waste.
_KEEPALIVE_ON = os.getenv("SPEAKER_KEEPALIVE", "1").strip().lower() not in {"0", "false", "no"}
_keepalive_started = False


# Level of the keep-alive noise, 0..1. Silence does NOT work: a cheap Bluetooth
# amp powers down after a few seconds of quiet and only wakes on an actual
# *signal*, so a silent stream feeds it exactly what puts it to sleep -- it naps
# straight through and still clips the first syllable. Very low-level broadband
# noise keeps the amp awake without being audible. ~0.002 (about -54 dBFS) is
# inaudible on most speakers; raise it if the first word still clips, lower it if
# you hear hiss. Learned from the chess-machine voice pipeline.
_KEEPALIVE_LEVEL = float(os.getenv("SPEAKER_KEEPALIVE_LEVEL", "0.002"))


def _keepalive_loop():
    import numpy as _np  # noqa: PLC0415

    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    # One second of low-level noise, looped. Noise, not a tone, because amp
    # detectors are broadband and noise cannot beat against anything audible.
    payload = (_np.random.default_rng(0).standard_normal(48000).astype("float32")
               * _KEEPALIVE_LEVEL).tobytes()
    step = 960 * 4  # 20 ms of float32 per write; realtime pw-play paces the loop
    while True:
        try:
            proc = subprocess.Popen(
                [PLAYER, "--raw", "--format=f32", "--rate=48000", "--channels=1", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env,
            )
            pos = 0
            while True:
                if pos + step > len(payload):
                    pos = 0
                proc.stdin.write(payload[pos:pos + step])
                pos += step
                if proc.poll() is not None:
                    break  # sink vanished (BT reconnecting) -> respawn
            time.sleep(1)
        except Exception:  # noqa: BLE001 - a comfort stream must never crash the app
            time.sleep(2)  # sink briefly gone; try again


def start_keepalive():
    """Begin the silent keep-alive stream once. Safe to call repeatedly."""
    global _keepalive_started
    if _keepalive_started or not _KEEPALIVE_ON:
        return
    _keepalive_started = True
    import threading  # noqa: PLC0415

    threading.Thread(target=_keepalive_loop, daemon=True, name="bt-keepalive").start()


def _lead_in_ms():
    if LEAD_IN_MS <= 0:
        return 0
    if time.monotonic() - _last_played > IDLE_SECONDS:
        return max(LEAD_IN_MS, COLD_LEAD_IN_MS)
    return LEAD_IN_MS

_kokoro = None


def get_engine():
    global _kokoro
    if _kokoro is None:
        _kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
    return _kokoro


def warm_up(voice=VOICE, speed=SPEED):
    get_engine().create("ready", voice=voice, speed=speed)


def play(samples, sample_rate, cold=False):
    audio = (np.clip(samples, -1.0, 1.0) * 32767).astype("int16")
    global _last_played
    lead_ms = max(_lead_in_ms(), COLD_LEAD_IN_MS) if cold else _lead_in_ms()
    if lead_ms > 0:
        lead = np.zeros(int(sample_rate * lead_ms / 1000), dtype="int16")
        audio = np.concatenate([lead, audio])
    tmp_path = os.path.join(tempfile.gettempdir(), f"kokoro-{os.getpid()}.wav")
    try:
        write(tmp_path, sample_rate, audio)
        # Hold the shared speaker lock across playback so the ghost's narration
        # (a separate process) waits its turn instead of playing on top. Blocking:
        # two voices talking over each other is worse than a pause.
        with audio_lock():
            subprocess.run([PLAYER, tmp_path], check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        # Fall back rather than lose the line; on HDMI it is at least audible.
        print(f"{PLAYER} playback failed ({e}), falling back to sounddevice")
        with audio_lock():
            sd.play(audio, sample_rate)
            sd.wait()
    finally:
        _last_played = time.monotonic()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def speak(text, voice=VOICE, speed=SPEED):
    if not text or not text.strip():
        return
    # Kokoro on the cluster when AUDIO_GATEWAY is set, the resident model
    # otherwise. It is the same 82M model either way, so the voice does not
    # change -- only where the ~10s of synthesis happens. get_engine() is lazy,
    # so a working gateway means the local weights are never loaded at all.
    clip = speak_remote(text, voice=voice)
    remote = clip is not None
    if clip is None:
        clip = get_engine().create(text, voice=voice, speed=speed)
    samples, sample_rate = clip
    # remote=True forces the cold lead-in: a gateway round trip is seconds long,
    # and the Bluetooth link sleeps during it, so even a line spoken moments
    # after the last one wakes to a cold speaker. The warm/cold timer only sees
    # the gap since playback *ended*, not the synthesis gap before this one.
    play(samples, sample_rate, cold=remote)


if __name__ == "__main__":
    speak("The goblin swings wide and the blade bites into the elf's shoulder.")


# Keep the Bluetooth link awake for the whole session.
start_keepalive()
