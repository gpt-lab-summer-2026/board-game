#!/usr/bin/env python3
"""Prove the cluster's model gateway works before wiring the voice loop to it.

    ./dnd-venv/bin/python check_gateway.py http://<gateway-host>:9000

Written against Host-Inference-Models' contract, not the OpenAI audio API:
`GET /health`, `GET /models`, and one `POST /generate` carrying a `model` id.
Text-to-speech answers with a URL rather than bytes, so the audio is a second
GET -- which is exactly the sort of thing worth finding out before a session
rather than during one.

Checks the three things that actually fail, in the order they fail:
reachability, then which model ids exist, then whether each direction round
trips. Prints the .env block to paste when they all pass.
"""
import base64
import io
import json
import os
import sys
import wave

TIMEOUT = 60


def probe(base: str, key: str) -> bool:
    import requests

    # One auth implementation, shared with the voice loop: a checker that signs
    # its own tokens differently from the client is a checker that can pass
    # while the real thing 401s.
    import os

    if key:
        os.environ["AUDIO_GATEWAY_KEY"] = key
    from ghost_client import _gateway_auth

    head = _gateway_auth()
    if os.getenv("MODEL_GATE_WAY_JWT_SECRET"):
        how = "HS256 JWT signed with MODEL_GATE_WAY_JWT_SECRET"
    elif head:
        how = "bearer key supplied"
    else:
        how = "none (as the open-source gateway documents)"
    ok = True
    print(f"gateway: {base}\nauth:    {how}\n")

    try:
        health = requests.get(f"{base}/health", headers=head, timeout=TIMEOUT)
        print(f"  GET /health -> {health.status_code} {health.text[:80]}")
    except Exception as e:
        print(f"  GET /health -> unreachable: {e}")
        return False

    # The ids here are the gateway's own, from registry.yaml. Guessing them
    # against a live endpoint is what wasted the most time last time.
    try:
        res = requests.get(f"{base}/models", headers=head, timeout=TIMEOUT)
        res.raise_for_status()
        body = res.json()
        entries = body.get("models") if isinstance(body, dict) else body
        ids = [m.get("id") or m.get("modelId") for m in (entries or [])]
    except Exception as e:
        print(f"  GET /models -> {e}")
        return False

    stt = os.getenv("STT_MODEL") or next((i for i in ids if i and "whisper" in i.lower()), None)
    tts = os.getenv("TTS_MODEL") or next((i for i in ids if i and "kokoro" in i.lower()), None)
    print(f"  GET /models -> {len(ids)} models")
    print(f"    whisper-ish: {[i for i in ids if i and 'whisper' in i.lower()] or 'none'}")
    print(f"    kokoro-ish:  {[i for i in ids if i and 'kokoro' in i.lower()] or 'none'}")

    # -- speech to text: a second of silence is enough to see the shape ------
    if stt is None:
        print("\n  no whisper model listed; set STT_MODEL and re-run")
        ok = False
    else:
        # A tone, not silence: an all-zero WAV makes whisper's frontend fail with
        # an InferenceError that looks like a dead backend. One second of 16 kHz
        # sine gives it something real to decode.
        import math
        import struct

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(16000)))
        body = {
            "model": stt,
            "audio": base64.b64encode(buf.getvalue()).decode("ascii"),
            "language": "en",
            "format": "json",
        }
        try:
            r = requests.post(f"{base}/generate", json=body, headers=head, timeout=TIMEOUT)
            print(f"\n  POST /generate ({stt}) -> {r.status_code}")
            print(f"    {r.text[:220]}")
            ok = ok and r.status_code == 200 and r.json().get("success") is not False
        except Exception as e:
            print(f"\n  POST /generate ({stt}) -> {e}")
            ok = False

    # -- text to speech: two round trips, and the second is the one that bites
    if tts is None:
        print("\n  no kokoro model listed; set TTS_MODEL and re-run")
        ok = False
    else:
        body = {
            "model": tts,
            "text": "The elf moves north.",
            "voice": os.getenv("TTS_VOICE", "af_heart"),
            "speed": 1.0,
            "format": "wav",
        }
        try:
            r = requests.post(f"{base}/generate", json=body, headers=head, timeout=TIMEOUT)
            print(f"\n  POST /generate ({tts}) -> {r.status_code}")
            payload = r.json() if r.content else {}
            print(f"    {json.dumps(payload)[:220]}")
            url = payload.get("output_url") or payload.get("public_output_url") or ""
            if "/outputs/" not in url:
                print("    no /outputs/ url in the reply")
                ok = False
            else:
                # Against the base we called, not the address in the body: a
                # backend addressed directly returns its own container address.
                fetch = f"{base}{url[url.index('/outputs/'):]}"
                a = requests.get(fetch, headers=head, timeout=TIMEOUT)
                riff = a.status_code == 200 and a.content[:4] == b"RIFF"
                print(f"    GET {fetch} -> {a.status_code}, {len(a.content)} bytes"
                      f"{', real WAV' if riff else ' -- NOT a WAV'}")
                ok = ok and riff
        except Exception as e:
            print(f"\n  POST /generate ({tts}) -> {e}")
            ok = False

    if ok:
        print("\nBoth directions work. Put this in dnd/python/.env:\n")
        print(f'AUDIO_GATEWAY = "{base}"')
        if key:
            print(f'AUDIO_GATEWAY_KEY = "{key}"')
        print(f'STT_MODEL = "{stt}"')
        print(f'TTS_MODEL = "{tts}"')
        print("\nThen restart main.py. No code changes.")
    else:
        print("\nNot right yet -- see above. Nothing to change in .env.")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(0 if probe(sys.argv[1].rstrip("/"), sys.argv[2] if len(sys.argv) > 2 else "") else 1)
