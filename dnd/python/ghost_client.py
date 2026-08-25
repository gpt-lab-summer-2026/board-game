import argparse
import requests

p = argparse.ArgumentParser(description="HTTP connection")
p.add_argument("--host", default="127.0.0.1", help="console bind address")
p.add_argument("--port", type=int, default=8770)
# parse_known_args, not parse_args: this runs at *import* time, so anything
# that imports this module inherits its argument parser. A plain parse_args
# made `check_gateway.py http://host:9000` die with "unrecognized arguments"
# for an argument that was never meant for it.
args, _ignored = p.parse_known_args()

def postReq(message):
    res = requests.post(f"http://{args.host}:{args.port}/command", json=message)
    print("post response status: ", res.status_code)
    return res.json()

def ghost_pending():
    """Is the ghost holding a yes/no question right now?

    Unreachable ghost counts as "no": a stray confirmation is worse than a
    refused one, since the ghost applies it to whatever it happens to be holding.
    """
    try:
        res = requests.get(f"http://{args.host}:{args.port}/pending", timeout=5)
        res.raise_for_status()
        return bool(res.json().get("awaiting"))
    except Exception:
        return False


def _busy_capture_devices():
    """Capture devices ALSA can see but nobody else can open, and who has them.

    Worth the twenty lines: an exclusively-held card does not appear in
    PortAudio's device list at all, so the symptom is "the microphone is gone"
    when the truth is "something else is recording with it". That sent us
    looking for a bad device index twice.

    /proc/asound is read directly because arecord and fuser tell you different
    halves of this and neither names the owning command.
    """
    import glob
    import os

    notes = []
    for status in sorted(glob.glob("/proc/asound/card*/pcm*c/sub*/status")):
        try:
            with open(status) as fh:
                body = fh.read()
        except OSError:
            continue
        if body.strip().startswith("closed"):
            continue
        card = status.split("/")[3]
        try:
            with open(f"/proc/asound/{card}/id") as fh:
                name = fh.read().strip()
        except OSError:
            name = card
        owner = ""
        for line in body.splitlines():
            if line.startswith("owner_pid"):
                pid = line.split(":")[-1].strip()
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as fh:
                        cmd = fh.read().replace(b"\0", b" ").decode().strip()
                except OSError:
                    cmd = "?"
                owner = f" held by pid {pid} ({cmd})"
        notes.append(f"{name}: in use{owner}")
    return notes or ["nothing is holding a capture device; the microphone is probably unplugged"]


def mic_device(name_hint="AK5370"):
    """The current index of the microphone, re-resolved every call.

    PortAudio enumerates devices once, when `sounddevice` is imported, and hands
    out indices into that snapshot. Connecting or disconnecting a Bluetooth
    speaker makes PipeWire rebuild its device list, so a long-running process
    keeps using indices that no longer mean what they did -- which surfaces as
    "error querying device 2" from a program that was working a minute earlier.

    So: tear PortAudio down, bring it back up, and find the microphone by name.
    Names survive a reshuffle; indices do not.

    Falls back to the system default input if the name is not found, and to None
    (which also means "system default") if the refresh itself fails -- being
    approximately right beats refusing to listen.
    """
    import sounddevice as sd

    try:
        sd._terminate()
        sd._initialize()
    except Exception as e:
        print("could not refresh the audio device list: ", e)

    try:
        devices = list(enumerate(sd.query_devices()))
    except Exception as e:
        print("could not enumerate audio devices: ", e)
        return None

    inputs = [(i, d) for i, d in devices if d["max_input_channels"] > 0]
    for index, dev in inputs:
        if name_hint.lower() in dev["name"].lower():
            return index

    # Named device absent. Any real input beats the system default, because on
    # this Pi ALSA reports default_input_device == -1 whenever the USB mic is
    # missing, and device=None then fails with a far less obvious error.
    if inputs:
        index, dev = inputs[0]
        print(f"microphone {name_hint!r} not found; falling back to {dev['name']!r}")
        return index

    print(f"no input devices at all -- {name_hint!r} is unplugged or busy.")
    for line in _busy_capture_devices():
        print("  ", line)
    return None


def getState():
    """The board as a table, for pasting into the system prompt.

    Returns an empty string if the ghost is unreachable rather than raising:
    losing the facts should degrade the translator to its old guessy self, not
    stop the game.
    """
    try:
        res = requests.get(f"http://{args.host}:{args.port}/state",
                           params={"format": "text"}, timeout=10)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print("state unavailable: ", e)
        return ""


def player_turn():
    """Is it a player character's turn right now?

    True when the active creature is on the party's side -- or when nobody is in
    initiative at all, so out of combat the wake word always works. Used to stop
    the voice loop prompting during the ghost's own monster turns: a table with
    one human running the party never acts on a goblin's turn, so the mic should
    not open then.

    Unreachable ghost -> True: better to listen than to go deaf if the console
    is briefly down.
    """
    try:
        res = requests.get(f"http://{args.host}:{args.port}/state", timeout=5)
        res.raise_for_status()
        state = res.json()
    except Exception:
        return True
    active = state.get("turn_of")
    if not active:
        return True
    char = (state.get("characters") or {}).get(active) or {}
    return char.get("side") == "party"


def getReq():
    res = requests.get(f"http://{args.host}:{args.port}/characters", )
    #print("get response: ", res.json()["characters"])
    # return list of characters
    return res.json()["characters"]

def post_to_cluster(url, payload):
    res = requests.post(url, json=payload)
    res.raise_for_status()
    return res.json()


#postReq({"command": "elf ranged attack on emo", "source":"voice "}

# --- remote speech -----------------------------------------------------------
#
# Whisper and Kokoro are the two slowest things on this Pi by a wide margin:
# measured, 8.5s to transcribe a 3.8s sentence and 9.8s to synthesise one, out
# of a ~26s round trip in which the 70b was the *fastest* neural step. Both
# models are on the cluster, behind its model gateway.
#
# Written against that gateway's actual contract (Host-Inference-Models), which
# is not the OpenAI audio API an earlier version of this guessed at:
#
#   POST {gateway}/generate   {"model": "<id>", ...fields...}
#
# The gateway strips `model` and forwards the remaining fields to whichever
# backend serves it, so one endpoint covers both directions and the model id is
# the only thing that changes. Two shapes come back:
#
#   speech-to-text -> JSON with the transcript inline
#   text-to-speech -> JSON with a URL; the audio is a second GET
#
# Nothing here changes behaviour until AUDIO_GATEWAY is set: every function
# returns None when it is unset or unreachable, and every caller falls back to
# the local model. A network blip degrades to slow, never to silent -- which
# matters more than the latency, because a table that has gone quiet has no way
# to ask what happened.

STT_DEFAULT = "distil-whisper-large-v3"
TTS_DEFAULT = "kokoro-82m"


def _b64u(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


# The gateway's own auth (model-gateway/auth.py, deployed on the cluster) checks
# an exact claim set, not the generic one an OpenAI-style bearer would carry:
#   iss == "sw4e-control-plane", aud == "model-gateway", an int exp in the
#   future, non-empty userId and tenantId, and non-empty string lists
#   permittedTasks and permittedModelIds -- all camelCase. /generate then also
#   checks the request's task and model_id are *inside* those two lists.
# So the token is per-capability, not just per-identity: it has to name what it
# is allowed to do. These defaults name exactly the two things the voice loop
# does; override via env if the control plane hands out narrower grants.
GATEWAY_ISSUER = "sw4e-control-plane"
GATEWAY_AUDIENCE = "model-gateway"


def _mint_jwt(secret: str) -> str:
    """An HS256 token matching the gateway's `verify_gateway_jwt`.

    By hand rather than with PyJWT: HS256 is a SHA-256 HMAC over two base64url
    segments, the standard library has both, and a dependency in the voice
    loop's venv for forty lines of well-specified format is the worse trade.

    `permittedModelIds` is built from whatever the .env points STT/TTS at, so a
    changed model id does not silently fall outside the grant. `permittedTasks`
    are the gateway's task names for the two directions.
    """
    import hashlib
    import hmac
    import json
    import os
    import time

    now = int(time.time())
    tts = (os.getenv("TTS_MODEL") or TTS_DEFAULT).strip()
    stt = os.getenv("STT_MODEL")
    stt = STT_DEFAULT if stt is None else stt.strip()
    # The gateway's task names, confirmed against the live registry: TTS is
    # "text-to-speech", but STT is "automatic-speech-recognition" -- NOT
    # "speech-to-text", which the gateway rejects with GATEWAY_SCOPE_DENIED. The
    # scope check compares these exactly, so the wrong string is a 403 that
    # looks like a permissions problem rather than a typo. Overridable in case a
    # future registry renames them.
    tasks, models = [], []
    if tts:
        tasks.append(os.getenv("TTS_TASK") or "text-to-speech")
        models.append(tts)
    if stt:
        tasks.append(os.getenv("STT_TASK") or "automatic-speech-recognition")
        models.append(stt)
    claims = {
        "iss": os.getenv("JWT_ISSUER") or GATEWAY_ISSUER,
        "aud": os.getenv("JWT_AUDIENCE") or GATEWAY_AUDIENCE,
        "iat": now,
        "exp": now + int(os.getenv("JWT_TTL_SECONDS") or 900),
        "userId": os.getenv("JWT_USER_ID") or "planarally-ghost",
        "tenantId": os.getenv("JWT_TENANT_ID") or "planarally",
        "permittedTasks": _csv_env("JWT_TASKS", tasks),
        "permittedModelIds": _csv_env("JWT_MODEL_IDS", models),
    }

    segments = [
        _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()),
        _b64u(json.dumps(claims, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return ".".join(segments + [_b64u(signature)])


def _csv_env(name: str, default: list) -> list:
    """A comma-separated env override, or the default list de-duplicated."""
    import os

    raw = (os.getenv(name) or "").strip()
    values = [v.strip() for v in raw.split(",") if v.strip()] if raw else list(default)
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return seen


def _gateway_auth():
    """Authorization header for the gateway, or {} when it wants none.

    Three cases, in the order they are tried:

    * MODEL_GATE_WAY_JWT_SECRET -- a *signing* secret, not a token. A fresh
      short-lived JWT is minted per call. Minting per call rather than caching
      one is deliberate: the calls are seconds apart and a stale `exp` is a
      401 that looks exactly like a wrong secret.
    * AUDIO_GATEWAY_KEY -- a ready-made bearer token, if they hand one out
      instead.
    * neither -- the open-source gateway documents itself as unauthenticated.
    """
    import os

    # The .env your coworker supplied spells it MODEL_GATE_WAY_JWT_SECRET (extra
    # underscore); the gateway's own code reads MODEL_GATEWAY_JWT_SECRET. Accept
    # either, preferring the one that is set, so neither spelling silently means
    # "no auth".
    secret = (
        os.getenv("MODEL_GATEWAY_JWT_SECRET")
        or os.getenv("MODEL_GATE_WAY_JWT_SECRET")
        or ""
    ).strip()
    if secret:
        try:
            return {"Authorization": f"Bearer {_mint_jwt(secret)}"}
        except Exception as e:
            print("could not sign a gateway token: ", e)
            return {}
    key = (os.getenv("AUDIO_GATEWAY_KEY") or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _gateway():
    """Base URL of the model gateway, or None.

    Read per call rather than at import: main.py calls load_dotenv() *after*
    importing this module, so anything captured at module scope would be the
    value from before the .env was read -- which is to say, nothing.
    """
    import os

    base = (os.getenv("AUDIO_GATEWAY") or "").strip().rstrip("/")
    return base or None


def _generate(base, body, timeout):
    """One POST /generate. Returns the parsed body, or None on any failure.

    None is the "use the local model" signal, and it deliberately covers every
    failure -- refused connection, timeout, non-200, malformed body, or a 200
    carrying the gateway's own {"success": false} error shape. There is no case
    where raising is better: the caller is a voice loop, and an exception there
    ends the session.
    """
    try:
        res = requests.post(
            f"{base}/generate", json=body, headers=_gateway_auth(), timeout=timeout
        )
        payload = res.json() if res.content else {}
    except Exception as e:
        print("model gateway unreachable: ", e)
        return None
    if res.status_code != 200 or payload.get("success") is False:
        # The gateway reports failures in the body rather than only by status,
        # so both have to be checked or a validation error reads as success.
        print("model gateway refused: ", payload.get("message") or res.status_code)
        return None
    return payload


def transcribe_remote(path, model=None, timeout=30):
    """Speech to text on the cluster. None if it cannot be done there.

    The audio goes as base64 in the JSON body rather than as a multipart upload:
    the ASR runner accepts a path, a data: URI or bare base64, and base64 is the
    only one of those three that means anything from another machine.
    """
    import base64
    import os

    import os

    base = _gateway()
    # Empty STT_MODEL means this gateway has no speech-to-text (the TUNI one is
    # TTS-only), so skip it and let the caller use the local model. Without this
    # every transcription would spend a round trip to be told the model is not
    # served, on the hot path, before falling back.
    stt = model or os.getenv("STT_MODEL")
    if base is None or (stt is not None and not str(stt).strip()):
        return None
    stt = stt or STT_DEFAULT
    try:
        with open(path, "rb") as fh:
            audio = base64.b64encode(fh.read()).decode("ascii")
    except OSError as e:
        print("could not read the recording: ", e)
        return None

    payload = _generate(base, {
        "model": stt,
        "audio": audio,
        "language": "en",
        "format": "json",
    }, timeout)
    if payload is None:
        return None

    text = payload.get("text") or payload.get("transcript")
    if not isinstance(text, str) or not text.strip():
        return None
    # The same trimming the local path does, so the two are interchangeable to
    # the caller: a trailing full stop changes what the command parser sees.
    return text.strip().rstrip(".!?,;:")


def speak_remote(text, voice=None, model=None, timeout=30):
    """Text to speech on the cluster, as (samples, sample_rate). None if not.

    Two round trips, because that is what the gateway offers: the POST returns a
    URL and the audio is fetched from it. `output_url` is rewritten by the
    gateway to point at itself, so it is resolved against the gateway base
    rather than against whichever backend actually rendered it.

    Decoded rather than handed back as bytes so the caller has one playback path
    for both sources -- which is what keeps the Bluetooth lead-in padding
    applying to remote audio too.
    """
    import os

    base = _gateway()
    if base is None or not text or not text.strip():
        return None

    payload = _generate(base, {
        "model": model or os.getenv("TTS_MODEL") or TTS_DEFAULT,
        "text": text,
        "voice": voice or os.getenv("TTS_VOICE") or "af_heart",
        "speed": float(os.getenv("TTS_SPEED") or 1.0),
        "format": "wav",
    }, timeout)
    if payload is None:
        return None

    # Resolve the audio against the host we just talked to, whatever the body
    # says. The gateway rewrites both url fields to point at itself, but a
    # backend addressed directly returns its *own* container address in
    # `public_output_url` -- which is routable inside Docker and nowhere else.
    # Taking only the /outputs/... path and hanging it off `base` is right in
    # both cases, and is what the gateway does internally.
    url = payload.get("output_url") or payload.get("public_output_url")
    if not isinstance(url, str) or "/outputs/" not in url:
        print("model gateway returned no audio url: ", url)
        return None
    url = f"{base}{url[url.index('/outputs/'):]}"

    try:
        audio = requests.get(url, headers=_gateway_auth(), timeout=timeout)
        audio.raise_for_status()

        import io

        from scipy.io.wavfile import read as wav_read

        sample_rate, samples = wav_read(io.BytesIO(audio.content))

        # Normalise to float in [-1, 1], which is what Kokoro returns locally
        # and therefore what play() is written against. A decoded WAV is
        # normally int16, and play() clips to [-1, 1] before scaling -- so
        # handing it raw int16 would flatten every sample to the rail and play
        # a square wave at full volume. Same contract from both sources, or the
        # fallback is not really a fallback.
        import numpy as np

        samples = np.asarray(samples)
        if samples.ndim > 1:  # a stereo gateway; the rest of the chain is mono
            samples = samples.mean(axis=1)
        if samples.dtype.kind == "i":
            samples = samples.astype("float32") / float(-np.iinfo(samples.dtype).min)
        elif samples.dtype.kind == "u":
            info = np.iinfo(samples.dtype)
            samples = (samples.astype("float32") - info.max / 2.0) / (info.max / 2.0)
        else:
            samples = samples.astype("float32")
    except Exception as e:
        print("could not fetch the synthesised audio: ", e)
        return None
    return samples, sample_rate


# --- one speaker at a time ---------------------------------------------------
#
# The voice loop (speak.py) and the ghost (voice/tts.py) are separate processes
# playing to the same speaker. Without coordination a slow ghost narration and a
# spoken SLM question land on top of each other. A blocking advisory lock on a
# shared path makes whoever wants to speak wait for whoever is speaking -- which
# is exactly "wait for the current speech to finish". Advisory `flock` is enough
# because both sides opt in; it costs nothing and needs no daemon.
AUDIO_LOCK_PATH = "/tmp/dnd-audio.lock"


class audio_lock:
    """Context manager: hold the speaker for the duration of one utterance."""

    def __enter__(self):
        import fcntl

        self._fh = open(AUDIO_LOCK_PATH, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX)
        except OSError:
            # A filesystem without flock (rare, but do not fail to speak over it).
            pass
        return self

    def __exit__(self, *exc):
        import fcntl

        try:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
        except OSError:
            pass
        self._fh.close()
        return False
