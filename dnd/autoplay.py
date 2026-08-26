#!/usr/bin/env python3
"""Hands-off demo: speak a player's command, then let the ghost resolve it.

One turn at a time, and nothing overlaps. Each beat is:

    pre-flight the command  ->  say it out loud  ->  post it to the ghost  ->
    wait out the ghost's narration (including any reaction)  ->  next turn

Three things here are load-bearing and none of them are obvious.

**The waiting.** The ghost narrates from a background task on its own schedule,
so posting a command and immediately posting the next one talks over the
previous answer. `wait_for_narration` watches the shared audio lock rather than
sleeping a guessed interval -- local Kokoro takes anywhere from two to twenty
seconds depending on how long the outcome is.

**The watching.** A background sampler records every transition of that lock, so
"did anything overlap?" is answered from evidence instead of from hope. Audio
cannot physically overlap -- both sides hold an exclusive flock -- but *order*
can still go wrong: if the ghost is still synthesising when we give up waiting,
its narration of turn N lands after turn N+1 has been announced. That is the
failure this instrumentation exists to catch, and it is invisible without it.

**The pre-flight.** A line that will be refused is worse than a line not spoken:
the table hears a command and watches nothing happen. Every beat is checked
against the board -- whose turn it is, what budget is left, whether the spell is
even on the sheet -- before anything is said out loud.

Every fault is logged with a code, to the console and to a JSONL file, and
summarised at the end. Run with the board up and a single ghost on :8770:

    python3 autoplay.py                # one full round
    python3 autoplay.py --rounds 2
    python3 autoplay.py --dry          # no audio, no commands; just the script
    python3 autoplay.py --no-roll      # keep the initiative already on the board
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, "python", ".env")
LOG_DIR = os.path.join(HERE, "logs")
GHOST = os.environ.get("GHOST_CONSOLE", "http://127.0.0.1:8770")
AUDIO_LOCK_PATH = "/tmp/dnd-audio.lock"

# Matches voice/tts.py: a Bluetooth amp gates on signal, so the pad in front of
# a line has to carry a little energy or the first syllable is eaten.
LEAD_IN_MS = int(os.getenv("AUTOPLAY_LEAD_MS", "700"))
LEAD_IN_LEVEL = float(os.getenv("AUTOPLAY_LEAD_LEVEL", "0.004"))

# How long to let the ghost think before deciding it is not going to narrate,
# and how long to let it talk once it has started.
NARRATION_START_TIMEOUT = float(os.getenv("AUTOPLAY_NARRATION_START", "30"))
NARRATION_END_TIMEOUT = float(os.getenv("AUTOPLAY_NARRATION_END", "180"))

# Block-buffered stdout hides the whole run until it exits, which makes a live
# demo impossible to follow and a hang impossible to diagnose.
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:  # pragma: no cover - very old Python
    pass


# --------------------------------------------------------------------------
# fault log


class Log:
    """Console narration plus a JSONL event stream, and a fault tally.

    Faults carry a stable code so a run can be diffed against the last one
    rather than re-read. `summary()` is what gets reported back.
    """

    def __init__(self, path: str | None) -> None:
        self.t0 = time.monotonic()
        self.faults: list[dict] = []
        self.counts: Counter = Counter()
        self.fh = None
        if path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                self.fh = open(path, "a", buffering=1)
            except OSError as e:
                print(f"[autoplay] cannot open the event log ({e}); console only")

    def _write(self, kind: str, **fields) -> None:
        rec = {"t": round(time.monotonic() - self.t0, 3), "kind": kind, **fields}
        if self.fh is not None:
            self.fh.write(json.dumps(rec) + "\n")

    def event(self, kind: str, **fields) -> None:
        self._write(kind, **fields)

    def info(self, text: str, **fields) -> None:
        print(f"      \033[90m{text}\033[0m")
        self._write("info", text=text, **fields)

    def spoke(self, text: str) -> None:
        print(f'  \033[36m"{text}"\033[0m')

    def turn(self, rnd, who) -> None:
        print(f"\n\033[1m— round {rnd}, {who}'s turn —\033[0m")
        self._write("turn", round=rnd, who=who)

    def fault(self, code: str, detail: str, **fields) -> None:
        self.counts[code] += 1
        rec = {"code": code, "detail": detail, **fields}
        self.faults.append(rec)
        print(f"      \033[31m[{code}]\033[0m {detail}")
        self._write("fault", **rec)

    def warn(self, code: str, detail: str, **fields) -> None:
        """A fault that is expected play, not a defect -- counted, not alarming."""
        self.counts[code] += 1
        self.faults.append({"code": code, "detail": detail, "benign": True, **fields})
        print(f"      \033[33m[{code}]\033[0m {detail}")
        self._write("fault", code=code, detail=detail, benign=True, **fields)

    def summary(self) -> None:
        print("\n\033[1m— fault summary —\033[0m")
        if not self.counts:
            print("  clean run: no faults recorded")
        for code, n in self.counts.most_common():
            print(f"  {n:3}x  {code}")
        self._write("summary", counts=dict(self.counts))
        if self.fh is not None:
            print(f"  events: {self.fh.name}")
            self.fh.close()


# --------------------------------------------------------------------------
# audio lock: who is talking, and when


def _lock_busy() -> bool:
    """Is somebody holding the shared speaker right now?"""
    try:
        with open(AUDIO_LOCK_PATH, "w") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
                return False
            except OSError:
                return True
    except OSError:
        return False


class LockWatch:
    """Samples the audio lock so overlap can be proven rather than assumed.

    Every busy stretch is attributed to whoever we know was holding it: this
    process while it is playing a command line, the ghost otherwise. The
    resulting timeline is what `check_ordering` reads to decide whether a
    narration arrived after the demo had already moved on.
    """

    def __init__(self, log: Log, interval: float = 0.1) -> None:
        self.log = log
        self.interval = interval
        self.segments: list[dict] = []
        self._ours = False
        self._busy_since: float | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="lockwatch")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def mine(self, on: bool) -> None:
        self._ours = on

    def _run(self) -> None:
        while not self._stop.is_set():
            busy = _lock_busy()
            now = time.monotonic() - self.log.t0
            if busy and self._busy_since is None:
                self._busy_since = now
                self._owner = "autoplay" if self._ours else "ghost"
            elif not busy and self._busy_since is not None:
                seg = {"owner": self._owner, "start": round(self._busy_since, 2),
                       "end": round(now, 2)}
                seg["seconds"] = round(seg["end"] - seg["start"], 2)
                self.segments.append(seg)
                self.log.event("speech", **seg)
                self._busy_since = None
            self._stop.wait(self.interval)

    def ghost_spoke_since(self, mark: float) -> bool:
        return any(s["owner"] == "ghost" and s["end"] > mark for s in self.segments)


# --------------------------------------------------------------------------
# the cluster gateway


def load_env(path: str = ENV_PATH) -> None:
    """Read python/.env without a dotenv dependency (no venv here has one)."""
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                # The real .env has `KEY = "value"   # trailing comment`, so a
                # bare strip('"') leaves the closing quote attached and the URL
                # parses with a port of `9000"`. Take the quoted span when there
                # is one, and cut an unquoted value at its comment.
                if v[:1] in {'"', "'"} and v.count(v[0]) >= 2:
                    v = v[1:v.index(v[0], 1)]
                else:
                    v = v.split("#", 1)[0].strip()
                os.environ.setdefault(k.strip(), v)
    except OSError as e:
        print(f"[autoplay] no .env ({e}); the gateway will be skipped")


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _mint_jwt(secret: str, model: str) -> str:
    """The gateway's exact claim set -- see ghost_client._mint_jwt."""
    now = int(time.time())
    claims = {
        "iss": "sw4e-control-plane",
        "aud": "model-gateway",
        "iat": now,
        "exp": now + 900,
        "userId": "planarally-autoplay",
        "tenantId": "planarally",
        "permittedTasks": ["text-to-speech"],
        "permittedModelIds": [model],
    }
    segs = [
        _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()),
        _b64u(json.dumps(claims, separators=(",", ":")).encode()),
    ]
    sig = hmac.new(secret.encode(), ".".join(segs).encode("ascii"), hashlib.sha256).digest()
    return ".".join(segs + [_b64u(sig)])


def _auth(model: str) -> dict:
    secret = (
        os.getenv("MODEL_GATEWAY_JWT_SECRET") or os.getenv("MODEL_GATE_WAY_JWT_SECRET") or ""
    ).strip()
    return {"Authorization": f"Bearer {_mint_jwt(secret, model)}"} if secret else {}


class Voice:
    """Speaks a line through the cluster, or degrades to printing it.

    Every failure mode is a distinct fault code, because "the demo went quiet"
    has half a dozen causes and they need different fixes: the tunnel being
    down is not the same as the token being wrong is not the same as pw-play
    missing.
    """

    def __init__(self, log: Log, watch: LockWatch | None) -> None:
        self.log = log
        self.watch = watch
        self.enabled = True
        base = (os.getenv("AUDIO_GATEWAY") or "").strip().rstrip("/")
        self.base = base or None
        self.model = (os.getenv("TTS_MODEL") or "kokoro-82m").strip()
        self.voice = os.getenv("KOKORO_VOICE") or "af_aoede"
        if self.base is None:
            self.log.fault("GATEWAY_NOT_CONFIGURED", "AUDIO_GATEWAY is unset; running silent")
            self.enabled = False
        if shutil.which("pw-play") is None:
            self.log.fault("PWPLAY_MISSING", "pw-play is not on PATH; running silent")
            self.enabled = False

    def synth(self, text: str):
        body = json.dumps({
            "model": self.model, "text": text, "voice": self.voice,
            "speed": 1.0, "format": "wav",
        }).encode()
        try:
            req = urllib.request.Request(
                f"{self.base}/generate", data=body,
                headers={"Content-Type": "application/json", **_auth(self.model)},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            self.log.fault("GATEWAY_REFUSED", f"HTTP {e.code}: {detail}")
            return None
        except Exception as e:  # noqa: BLE001
            self.log.fault("GATEWAY_UNREACHABLE", f"{type(e).__name__}: {e}")
            return None

        if payload.get("success") is False:
            self.log.fault("GATEWAY_REFUSED", str(payload.get("message"))[:200])
            return None
        url = payload.get("output_url") or payload.get("public_output_url")
        if not isinstance(url, str) or "/outputs/" not in url:
            self.log.fault("GATEWAY_NO_URL", f"no audio url in the reply: {url!r}")
            return None

        try:
            req = urllib.request.Request(
                f"{self.base}{url[url.index('/outputs/'):]}", headers=_auth(self.model)
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except Exception as e:  # noqa: BLE001
            self.log.fault("AUDIO_FETCH_FAILED", f"{type(e).__name__}: {e}")
            return None

        try:
            with wave.open(io.BytesIO(raw)) as w:
                frames = w.readframes(w.getnframes())
                rate, width, chans = w.getframerate(), w.getsampwidth(), w.getnchannels()
        except Exception as e:  # noqa: BLE001
            self.log.fault("WAV_DECODE_FAILED", f"{type(e).__name__}: {e}")
            return None

        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(width)
        if dtype is None:
            self.log.fault("UNSUPPORTED_SAMPLE_WIDTH", f"{width} bytes per sample")
            return None
        samples = np.frombuffer(frames, dtype=dtype).astype("float32")
        samples /= float(np.iinfo(dtype).max)
        if chans > 1:
            samples = samples.reshape(-1, chans).mean(axis=1)
        if samples.size == 0:
            self.log.fault("EMPTY_AUDIO", "the gateway returned a zero-length clip")
            return None
        return samples, rate

    def play(self, samples, rate: int) -> None:
        frames = int(rate * LEAD_IN_MS / 1000)
        if frames > 0:
            pad = (np.random.default_rng(0).standard_normal(frames)
                   * LEAD_IN_LEVEL).astype("float32")
            samples = np.concatenate([pad, samples.astype("float32")])

        env = dict(os.environ)
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

        waited = time.monotonic()
        if self.watch:
            self.watch.mine(True)
        try:
            with open(AUDIO_LOCK_PATH, "w") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                blocked_ms = int((time.monotonic() - waited) * 1000)
                if blocked_ms > 500:
                    # We only reach here after wait_for_narration said the ghost
                    # was done, so a real wait means it started talking again.
                    self.log.fault(
                        "SPEAKER_CONTENDED",
                        f"waited {blocked_ms}ms for the speaker; something else was talking",
                        blocked_ms=blocked_ms,
                    )
                try:
                    p = subprocess.Popen(
                        ["pw-play", "--raw", "--format=f32", f"--rate={rate}",
                         "--channels=1", "-"],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE, env=env,
                    )
                    p.stdin.write(samples.astype("float32").tobytes())
                    p.stdin.close()
                    rc = p.wait(timeout=120)
                    if rc != 0:
                        err = (p.stderr.read() or b"")[:200].decode("utf-8", "replace")
                        self.log.fault("PWPLAY_FAILED", f"exit {rc}: {err}")
                except subprocess.TimeoutExpired:
                    self.log.fault("PLAY_TIMEOUT", "pw-play did not finish within 120s")
                    p.kill()
                except Exception as e:  # noqa: BLE001
                    self.log.fault("PLAY_FAILED", f"{type(e).__name__}: {e}")
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            if self.watch:
                self.watch.mine(False)

    def say_plain(self, text: str) -> None:
        """Speak something already printed -- the DM's flavour line."""
        if not self.enabled:
            return
        clip = self.synth(text)
        if clip is not None:
            self.play(*clip)

    def say(self, text: str, dry: bool = False) -> None:
        self.log.spoke(text)
        self.log.event("say", text=text)
        if dry or not self.enabled:
            return
        t = time.monotonic()
        clip = self.synth(text)
        synth_ms = int((time.monotonic() - t) * 1000)
        if clip is None:
            self.log.event("say_silent", text=text, synth_ms=synth_ms)
            return
        self.log.event("say_synth", text=text, synth_ms=synth_ms,
                       seconds=round(len(clip[0]) / clip[1], 2))
        self.play(*clip)


# Commands that move the game along without anybody doing anything in the
# fiction. Handing these to the narrator produces invented events: "next turn"
# came back as "Weirdo readies their spell, unleashing a spectral force that
# envelops their foe", which no dice had rolled and no player had asked for.
_BOOKKEEPING = (
    "roll initiative", "next turn", "previous turn", "end turn", "clear initiative",
    "end combat", "long rest", "short rest", "dm auto", "teleport", "clear ",
    "set round", "undo", "target ",
)


def _is_bookkeeping(command: str) -> bool:
    lowered = command.strip().lower()
    return any(lowered.startswith(p) or lowered == p.strip() for p in _BOOKKEEPING)


def _roles(command: str) -> tuple[str, str | None]:
    """(actor, target) out of a command line, for the flavour prompt.

    Crude on purpose -- the actor is always the first word in this grammar, and
    the target is whatever follows the last preposition. Good enough to stop a
    small model narrating the victim as the aggressor.
    """
    words = command.strip().split()
    actor = words[0] if words else "the character"
    lowered = [w.lower() for w in words]
    for prep in ("on", "from", "to", "at"):
        if prep in lowered:
            tail = words[len(lowered) - 1 - lowered[::-1].index(prep) + 1:]
            if tail:
                return actor, " ".join(tail)
    # "elf attacks gentelman" -- no preposition, so the target trails the verb.
    if len(words) >= 3:
        return actor, words[-1]
    return actor, None


# --------------------------------------------------------------------------
# the cluster model


class Cluster:
    """llama3.3:70b on the cluster, for flavour and for choosing.

    Same endpoint the ghost uses (`python/.env: cluster_url`), so there is one
    address to change. Every call is best-effort: a dead cluster degrades the
    demo to plain mechanical narration rather than stopping it, and says so with
    a fault code rather than silently.
    """

    # A sentence of prose does not need a 70b, and the big one is frequently
    # unloadable -- the cluster's GPUs are shared, and `llama3.3:70b` (42 GB)
    # answers "CUDA error: out of memory" whenever somebody else has them. The
    # chain is tried in order and the first model that answers is kept for the
    # rest of the run, so one OOM costs one request, not one per line.
    FALLBACKS = ["mistral:7b-instruct", "qwen3:8b", "llama3.1:8b", "llama3.2:3b"]

    def __init__(self, log: Log) -> None:
        self.log = log
        self.url = self._resolve()
        preferred = os.getenv("AUTOPLAY_FLAVOUR_MODEL")
        self.candidates = [preferred] if preferred else list(self.FALLBACKS)
        self.model = self.candidates[0]
        self.enabled = self.url is not None
        if not self.enabled:
            self.log.warn("CLUSTER_NOT_CONFIGURED", "no cluster_url; no flavour narration")

    @staticmethod
    def _resolve() -> str | None:
        direct = os.getenv("GHOST_CLUSTER_URL") or os.getenv("cluster_url")
        return direct.strip() if direct else None

    def _once(self, model: str, prompt: str, timeout: float, temperature: float):
        """(text, retryable). `retryable` means try the next model, not give up."""
        body = json.dumps({
            "model": model,
            "stream": False,
            "think": False,
            "options": {"num_ctx": 8192, "temperature": temperature},
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        try:
            req = urllib.request.Request(
                self.url, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            # Out of memory is about this model's size, not about the cluster
            # being broken, so a smaller one is worth trying.
            if "out of memory" in detail.lower() or "cuda error" in detail.lower():
                self.log.warn("CLUSTER_MODEL_OOM", f"{model} will not load: {detail[:90]}")
                return None, True
            self.log.fault("CLUSTER_HTTP_ERROR", f"HTTP {e.code} from {model}: {detail[:90]}")
            return None, False
        except TimeoutError:
            self.log.fault("CLUSTER_TIMEOUT", f"{model} did not answer within {timeout}s")
            return None, True
        except Exception as e:  # noqa: BLE001
            self.log.fault("CLUSTER_UNREACHABLE", f"{type(e).__name__}: {e}")
            return None, False

        if isinstance(payload, dict) and payload.get("error"):
            detail = str(payload["error"])[:200]
            retry = "out of memory" in detail.lower() or "cuda error" in detail.lower()
            code = "CLUSTER_MODEL_OOM" if retry else "CLUSTER_ERROR"
            (self.log.warn if retry else self.log.fault)(code, f"{model}: {detail[:90]}")
            return None, retry

        text = str((payload.get("message") or {}).get("content") or "").strip()
        if not text:
            self.log.fault("CLUSTER_EMPTY", f"{model} replied with nothing")
            return None, True
        return text, False

    def chat(self, prompt: str, timeout: float = 30, temperature: float = 0.8) -> str | None:
        if not self.enabled:
            return None
        # The model that worked last time first, then the rest of the chain.
        order = [self.model] + [m for m in self.candidates if m != self.model]
        for model in order:
            text, retryable = self._once(model, prompt, timeout, temperature)
            if text is not None:
                if model != self.model:
                    self.log.event("cluster_model_switch", frm=self.model, to=model)
                self.model = model
                return text
            if not retryable:
                return None
        self.log.fault("CLUSTER_ALL_MODELS_FAILED",
                       f"none of {order} would answer; no flavour narration")
        self.enabled = False
        return None

    def flavour(self, command: str, lines: list[str]) -> str | None:
        """One vivid sentence for what just happened at the table.

        Constrained hard on purpose. The mechanical read-out has already been
        spoken by the ghost, so this must add colour without repeating numbers
        or contradicting the outcome -- a model left loose will happily narrate
        a kill that the dice did not produce.
        """
        if not lines:
            return None
        result = " ".join(lines)

        # Spelling out who acts on whom, rather than leaving it implicit in the
        # command, because a small model reverses them otherwise: "freak attacks
        # cat" came back as the cat doing the attacking. The roles are the one
        # thing the sentence cannot get wrong.
        actor, target = _roles(command)
        who = f"The one acting is {actor}."
        if target and target != actor:
            who += f" It is happening to {target}. {target} is NOT the one acting."

        prompt = (
            "You are the dungeon master narrating a Dungeons & Dragons fight out loud.\n"
            f"The player declared: {command}\n"
            f"{who}\n"
            f"The rules resolved it as: {result}\n\n"
            "Write ONE short sentence describing what that looked like, in the "
            "present tense.\n"
            "Rules for your sentence:\n"
            f"- {actor} is the one performing the action. Do not swap them round.\n"
            "- Never contradict the outcome above. A miss must sound like a miss, "
            "a kill like a kill, a heal like a heal, a retreat like a retreat.\n"
            "- Third person only. Never write \"you\" or \"your\".\n"
            "- Nobody's gender is known. Use \"they\" and \"them\" for every "
            "character, never \"he\", \"she\", \"his\" or \"her\".\n"
            "- Do not repeat any numbers, dice, hit points, armour class, feet or "
            "rules terms.\n"
            "- Do not add events that did not happen.\n"
            "- No preamble, no quotation marks, no name label. Just the sentence.\n"
        )
        text = self.chat(prompt, timeout=25, temperature=0.85)
        if text is None:
            return None
        # A model told to write one sentence sometimes writes three; take the
        # first and cap it, so a runaway reply cannot hijack the pacing.
        first = text.replace("\n", " ").strip().strip('"')
        for stop in (". ", "! ", "? "):
            if stop in first:
                first = first[: first.index(stop) + 1]
                break
        if len(first) > 240:
            self.log.warn("FLAVOUR_TRUNCATED", f"{len(first)} chars; cut to 240")
            first = first[:240].rsplit(" ", 1)[0] + "."
        return first or None

    def choose(self, who: str, options: list[str], board: str) -> int | None:
        """Pick one of the numbered options, or None to use the scripted plan."""
        listing = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(options))
        prompt = (
            f"You are playing {who} in a Dungeons & Dragons fight.\n"
            f"{board}\n\n"
            f"Choose {who}'s next action from this list:\n{listing}\n\n"
            "Answer with the number alone and nothing else."
        )
        text = self.chat(prompt, timeout=30, temperature=0.3)
        if text is None:
            return None
        digits = "".join(c for c in text if c.isdigit() or c == " ").split()
        if not digits:
            self.log.fault("CLUSTER_BAD_PICK", f"no number in {text[:60]!r}")
            return None
        index = int(digits[0])
        if not 1 <= index <= len(options):
            self.log.fault("CLUSTER_BAD_PICK", f"{index} is outside 1..{len(options)}")
            return None
        return index - 1


# --------------------------------------------------------------------------
# the ghost


class Ghost:
    """The ghost's HTTP console, with patience for it being restarted.

    A bare connection refused (errno 111) is nearly always the ghost being
    bounced to pick up new code -- it is down for fifteen to twenty-five seconds
    while Kokoro loads. Failing the run on that turns a routine restart into a
    dead demo, so a refused connection is waited out and retried; only a refusal
    that outlasts the whole window is a fault.

    Retrying is safe here precisely *because* it is a refused connection: the
    request never reached the ghost, so nothing was executed twice. A timeout is
    different -- the command may well have landed -- so those are reported, not
    replayed.
    """

    RECONNECT_SECONDS = float(os.getenv("AUTOPLAY_RECONNECT", "45"))

    def __init__(self, log: Log) -> None:
        self.log = log
        self._warned_down = False

    def _with_retry(self, make_request, what: str, timeout: float):
        deadline = time.monotonic() + self.RECONNECT_SECONDS
        attempt = 0
        while True:
            attempt += 1
            try:
                with urllib.request.urlopen(make_request(), timeout=timeout) as r:
                    payload = json.loads(r.read())
                if attempt > 1:
                    self.log.warn("GHOST_RECONNECTED",
                                  f"the console came back after {attempt - 1} retries")
                    self._warned_down = False
                return payload
            except urllib.error.HTTPError as e:
                self.log.fault("GHOST_HTTP_ERROR", f"HTTP {e.code} on {what}")
                return None
            except TimeoutError:
                # Possibly executed. Never replayed.
                self.log.fault("GHOST_TIMEOUT", f"no reply within {timeout}s to {what}")
                return None
            except urllib.error.URLError as e:
                refused = isinstance(e.reason, ConnectionRefusedError) or "refused" in str(e.reason)
                if not refused or time.monotonic() >= deadline:
                    self.log.fault("GHOST_UNREACHABLE", f"{what}: {e.reason}")
                    return None
                if not self._warned_down:
                    self.log.warn("GHOST_RESTARTING",
                                  "the console is refusing connections; waiting for it to come back")
                    self._warned_down = True
                time.sleep(2)
            except Exception as e:  # noqa: BLE001
                self.log.fault("GHOST_UNREACHABLE", f"{what}: {type(e).__name__}: {e}")
                return None

    def post(self, command: str, timeout: float = 90) -> dict | None:
        body = json.dumps({"command": command, "source": "voice"}).encode()

        def make():
            return urllib.request.Request(
                f"{GHOST}/command", data=body, headers={"Content-Type": "application/json"}
            )

        return self._with_retry(make, repr(command), timeout)

    def state(self) -> dict:
        got = self._with_retry(lambda: urllib.request.Request(f"{GHOST}/state"), "/state", 15)
        return got if isinstance(got, dict) else {}


# Why a command was refused, from the sentence the ghost refused it with. Used
# to tell an expected refusal (a wall, a spent action) from a defect.
REFUSAL_CODES = [
    ("that went wrong", "GHOST_INTERNAL_ERROR"),
    ("no line of sight", "REFUSED_NO_SIGHT"),
    ("not in reach", "REFUSED_NOT_IN_REACH"),
    ("has already used its", "REFUSED_NO_BUDGET"),
    ("no level", "REFUSED_NO_SLOT"),
    # "is not carrying" is the ghost's exact wording (actions.py:539). A looser
    # "has no " matched "has no movement left" too and filed it as a missing
    # potion -- the classifier has to be as specific as the message it reads.
    ("is not carrying", "REFUSED_NO_ITEM"),
    ("no movement left", "REFUSED_NO_MOVEMENT"),
    ("is not", "REFUSED_TURN_GUARD"),
    ("who is acting", "REFUSED_UNPARSED"),
    ("i heard", "REFUSED_UNPARSED"),
]


def classify_refusal(lines: list[str]) -> str:
    joined = " ".join(str(l).lower() for l in lines)
    for needle, code in REFUSAL_CODES:
        if needle in joined:
            return code
    return "REFUSED_OTHER"


# --------------------------------------------------------------------------
# the demo runner


class Autoplay:
    def __init__(self, log: Log, voice: Voice, ghost: Ghost, watch: LockWatch,
                 cluster: Cluster, dry: bool, flavour: bool = True) -> None:
        self.log, self.voice, self.ghost, self.watch = log, voice, ghost, watch
        self.cluster, self.dry = cluster, dry
        self.flavour = flavour and cluster.enabled

    def run_command(self, command: str) -> dict:
        """Post one command, print the answer, and classify any refusal."""
        if self.dry:
            print(f"      -> (dry) {command}")
            return {"ok": True, "lines": [], "dry": True}
        t = time.monotonic()
        body = self.ghost.post(command)
        elapsed = int((time.monotonic() - t) * 1000)
        if body is None:
            return {"ok": False, "lines": [], "code": "GHOST_UNREACHABLE"}

        entry = (body.get("entries") or [{}])[0]
        lines = [str(l) for l in (entry.get("lines") or [])]
        for line in lines:
            self.log.info(line)
        self.log.event("command", command=command, ok=bool(entry.get("ok")),
                       ms=elapsed, lines=lines)

        if not entry.get("ok"):
            code = classify_refusal(lines)
            entry["code"] = code
            detail = f"{command!r}: {lines[0] if lines else 'no reason given'}"
            # A wall or a spent action is the rules working. A traceback is not.
            if code in {"GHOST_INTERNAL_ERROR", "REFUSED_UNPARSED", "REFUSED_OTHER"}:
                self.log.fault(code, detail)
            else:
                self.log.warn(code, detail)
        entry["lines"] = lines
        return entry

    def wait_for_narration(self, expected: bool) -> None:
        """Block until the ghost has finished speaking this outcome.

        Two phases, because the ghost synthesises *before* it takes the lock:
        wait for it to start, then wait for it to finish. A flat sleep cannot do
        this -- local Kokoro takes two to twenty seconds depending on length.
        """
        if self.dry:
            return
        started = False
        deadline = time.monotonic() + NARRATION_START_TIMEOUT
        while time.monotonic() < deadline:
            if _lock_busy():
                started = True
                break
            time.sleep(0.1)

        if not started:
            if expected:
                # The next command will be spoken over this one when it finally
                # arrives. This is the ordering bug, caught at its source.
                self.log.fault(
                    "NARRATION_NEVER_STARTED",
                    f"nothing was spoken within {NARRATION_START_TIMEOUT:.0f}s of an "
                    "outcome that had lines; the next line may talk over it",
                )
            return

        deadline = time.monotonic() + NARRATION_END_TIMEOUT
        while time.monotonic() < deadline:
            if not _lock_busy():
                time.sleep(0.4)  # let the sink drain before the next line
                return
            time.sleep(0.1)
        self.log.fault("NARRATION_TIMEOUT",
                       f"the ghost was still speaking after {NARRATION_END_TIMEOUT:.0f}s")

    def _resolve(self, command: str) -> dict:
        """Post one command, then narrate the flavour over the top of the wait.

        The flavour sentence is fetched on a worker thread *while* the ghost is
        still reading out the mechanical result, so the cluster round trip costs
        no wall-clock at all -- by the time the ghost stops talking the sentence
        is already waiting. Doing it afterwards would add a visible pause to
        every single action.
        """
        entry = self.run_command(command)
        lines = entry.get("lines") or []

        box: dict = {}
        worker = None
        if self.flavour and lines and not self.dry and not _is_bookkeeping(command):
            def fetch() -> None:
                box["text"] = self.cluster.flavour(command, lines)

            worker = threading.Thread(target=fetch, daemon=True, name="flavour")
            worker.start()

        self.wait_for_narration(expected=bool(lines))

        if worker is not None:
            worker.join(timeout=30)
            if worker.is_alive():
                self.log.warn("FLAVOUR_SLOW", "the cluster did not answer in time")
            text = box.get("text")
            if text:
                print(f"  \033[35m{text}\033[0m")
                self.log.event("flavour", command=command, text=text)
                self.voice.say_plain(text)
        return entry

    def beat(self, spoken: str, command: str | None = None,
             alternatives: list[str] | None = None) -> dict:
        """Say a line, run it, and wait out the answer. The unit of the demo."""
        self.voice.say(spoken, dry=self.dry)
        entry = self._resolve(command if command is not None else spoken)

        for alt in alternatives or []:
            if entry.get("code") != "REFUSED_NO_SIGHT":
                break
            self.log.info(f"(no shot -- trying {alt!r})")
            self.voice.say(alt, dry=self.dry)
            entry = self._resolve(alt)
        return entry

    def take_sole_control(self) -> None:
        """Stop the ghost from playing the monsters while the demo is running.

        The ghost auto-runs any DM-controlled creature the moment `next turn`
        lands on one (`console.py:524`, on by default). With autoplay also
        speaking a line for that same monster, the turn has two drivers: the
        board gets both commands, and the ghost's narration of its own move is
        still playing when autoplay announces a different one. That is the
        overlap -- of control, not just of audio -- and it showed up as the same
        attack appearing twice in the ghost's log.

        The demo voices every creature, monsters included, so the ghost stands
        down for the duration and is handed the monsters back at the end.
        """
        if self.dry:
            return
        entry = self.run_command("dm auto off")
        if not entry.get("ok"):
            self.log.fault("DM_AUTO_NOT_RELEASED",
                           "could not stop the ghost running the monsters; "
                           "expect duplicated monster turns")

    def return_control(self) -> None:
        if self.dry:
            return
        self.run_command("dm auto on")

    def check_ordering(self, mark: float, label: str) -> None:
        """Did the ghost start talking after we had already moved on?"""
        if self.dry:
            return
        if self.watch.ghost_spoke_since(mark):
            return
        self.log.event("no_narration", after=label)


# --------------------------------------------------------------------------
# what each character does on its turn

# Mirrors ghost/actions._CASTING_TIME_5E so a line can be skipped before it is
# spoken. Kept deliberately small: anything absent is an action, the 5e default.
CASTING_TIME = {
    "shield of faith": "bonus",
    "healing word": "bonus",
    "shield": "reaction",
    "hex": "bonus",
    "hunter's mark": "bonus",
}


# Starting cells, in the grid's axial (q, r). Party to the right, goblins to the
# left, hamster on the far right, everyone inside one open hall.
#
# The first attempt put the sides in opposite corners of the map, which is what
# was asked for and what the board looked like it could support. Once the wall
# polygons were actually being rasterised it turned out they could not: the
# corners are 140-238 feet apart with masonry between them, eleven of the twelve
# cross-side pairs had no line of sight, and at 30 feet a round the first five
# to eight rounds were nothing but walking. A demo of the rules cannot start
# with eight rounds of no rules.
#
# So the arrangement is kept -- party one side, goblins the other, the hamster
# apart from both -- but scaled to a hall where every cross-side pair is clear
# and 14 to 56 feet apart. Everything is in range from the first turn.
#
# Recompute if the walls move -- see `tools/survey_map.py`.
START_CELLS = {
    "elf": (65, -44),
    "emo": (63, -43),
    "cat": (64, -42),
    "freak": (57, -41),
    "gentelman": (59, -41),
    "weirdo": (61, -42),
    "hamster": (67, -43),
}


def reset_board(demo: "Autoplay", ghost: Ghost, log: Log) -> None:
    """Put the board back to a known opening position.

    Hit points, spell slots and rages come back with a long rest; conditions
    have to be taken off one at a time because nothing clears them wholesale;
    positions are set with `teleport`, which is the only command that takes a
    cell rather than a creature to walk towards.

    Every teleport is verified afterwards. A token that did not move is a fault
    worth seeing before the demo starts rather than discovering mid-fight --
    usually it means the cell is inside a wall.
    """
    log.event("reset_start")
    print("\n\033[1m— resetting the board —\033[0m")

    demo.run_command("long rest")

    st = ghost.state()
    for name, c in (st.get("characters") or {}).items():
        for cond in c.get("conditions") or []:
            demo.run_command(f"clear {cond} from {name}")

    for name, (q, r) in START_CELLS.items():
        if name not in (st.get("characters") or {}):
            log.warn("RESET_UNKNOWN_CHARACTER", f"{name} is not on this board")
            continue
        demo.run_command(f"teleport {name} to {q},{r}")

    after = ghost.state()
    for name, (q, r) in START_CELLS.items():
        cell = (after.get("characters") or {}).get(name, {}).get("cell")
        if cell is None:
            continue
        if list(cell) != [q, r]:
            log.fault("RESET_PLACEMENT_FAILED",
                      f"{name} wanted ({q},{r}) but sits at {tuple(cell)}; "
                      "the cell is probably inside a wall")
    log.event("reset_done")


# Who carries what worth drinking, from the catalogue-joined inventories on
# these sheets. Party and monsters alike: the goblins bought potions too.
# Quantities run down as they are used and a long rest does not restock them,
# so an empty pack is refused by the ghost and logged as expected play rather
# than pretended around -- run tools/restock.py to fill them back up.
POTIONS = {
    "elf": "potion of healing",
    "emo": "potion of greater healing",
    "freak": "potion of greater healing",
    "gentelman": "potion of healing",
}


def _hit_points(char: dict | None) -> tuple[int, int]:
    """(current, max) out of the state's "7/10" string, or (0, 0)."""
    raw = str((char or {}).get("hp") or "")
    try:
        now, top = raw.split("/", 1)
        return int(now), int(top)
    except ValueError:
        return 0, 0


def plan(name: str, st: dict) -> list[tuple]:
    """(spoken, command[, alternatives]) for one creature's turn.

    Written against what these sheets actually carry -- elf has Magic Missile
    and Shield, emo has Shield of Faith and Guiding Bolt, freak is a barbarian
    who can rage -- so every line is a legal option rather than a hopeful one.
    Each turn spends a bonus action as well as an action where the character has
    something worth spending it on, and moves when it has somewhere to be.
    """
    chars = st.get("characters") or {}

    def alive(names: list[str]) -> list[str]:
        out = []
        for n in names:
            try:
                if int(str((chars.get(n) or {}).get("hp") or "0/0").split("/")[0]) > 0:
                    out.append(n)
            except ValueError:
                pass
        return out

    hostiles = [n for n, c in chars.items() if c.get("side") == "hostile"]
    party = [n for n, c in chars.items() if c.get("side") == "party"]
    foes = alive(hostiles) or hostiles or ["hamster"]
    allies = alive(party) or party or ["cat"]
    foe = foes[0]

    def retries(who: str, verb: str, pool: list[str]) -> list[str]:
        """Spoken retries at other targets, for when a wall is in the way."""
        return [f"{who} {verb} {n}" for n in pool[1:3]]

    def line(text: str) -> tuple:
        return (text, text)

    # Drinking a potion is a bonus action (see ghost/actions._do_use_item), so a
    # wounded creature can heal *and* still act. Monsters carry them too and use
    # them on the same terms -- freak's Potion of Greater Healing is the reason
    # a barbarian at 4 hit points is not simply finished.
    hp_now, hp_max = _hit_points(chars.get(name))
    hurt = hp_max > 0 and hp_now / hp_max <= 0.5
    opening: list[tuple] = []
    potion = POTIONS.get(name)
    if hurt and potion and not (st.get("budget") or {}).get("bonus"):
        opening.append(line(f"{name} drinks {potion}"))

    if name == "emo":
        ally = next((n for n in allies if n != "emo"), "cat")
        return opening + [
            line(f"emo casts shield of faith on {ally}"),
            (f"emo casts guiding bolt on {foe}", f"emo casts guiding bolt on {foe}",
             retries("emo", "casts guiding bolt on", foes)),
            line(f"emo moves away from {foe}"),
        ]
    if name == "elf":
        return opening + [
            (f"elf casts magic missile on {foe}", f"elf casts magic missile on {foe}",
             retries("elf", "casts magic missile on", foes)),
            line(f"elf moves away from {foe}"),
        ]
    if name == "cat":
        return opening + [line(f"cat attacks {foe}")]
    if name == "freak":
        mark = allies[0]
        return opening + [line("freak rages"), line(f"freak attacks {mark}")]
    if name == "gentelman":
        mark = allies[0]
        return opening + [
            (f"gentelman attacks {mark}", f"gentelman attacks {mark}",
             retries("gentelman", "attacks", allies)),
            line(f"gentelman moves away from {mark}"),
        ]
    if name == "weirdo":
        mark = allies[0]
        return opening + [
            (f"weirdo casts ray of frost on {mark}", f"weirdo casts ray of frost on {mark}",
             retries("weirdo", "casts ray of frost on", allies)),
            line(f"weirdo moves away from {mark}"),
        ]
    if name == "hamster":
        return opening + [line(f"hamster attacks {allies[0]}")]
    return opening + [line(f"{name} dodges")]


def preflight(command: str, who: str, st: dict, log: Log) -> str | None:
    """Why this line should not be spoken, or None to go ahead.

    A refused line is worse than a skipped one: the table hears a command and
    watches nothing happen. Everything cheap to check is checked here.
    """
    chars = st.get("characters") or {}
    lower = command.lower()

    actor = command.split(" ", 1)[0].lower()
    if actor not in {n.lower() for n in chars}:
        return f"no character called {actor!r} on the board"
    if actor != (who or "").lower():
        return f"it is {who}'s turn, not {actor}'s"

    # A creature at 0 hit points is unconscious: it rolls a death save and does
    # nothing else (PHB 197). Nothing stopped the demo from walking a dying cat
    # across the room, which looks like the rules being ignored at exactly the
    # dramatic moment everybody is watching.
    hp_now, hp_max = _hit_points(chars.get(who))
    if hp_max > 0 and hp_now <= 0:
        return f"{who} is down at 0 hit points and can only roll a death save"

    budget = st.get("budget") or {}
    if " casts " in lower:
        spell = lower.split(" casts ", 1)[1].split(" on ")[0].strip()
        sheet_spells = {str(s).lower() for s in (chars.get(who) or {}).get("spells") or []}
        cantrip = str((chars.get(who) or {}).get("cantrip") or "").lower()
        if spell not in sheet_spells and spell != cantrip:
            return f"{who} does not have {spell!r} prepared"
        cost = CASTING_TIME.get(spell, "action")
        if cost in ("action", "bonus") and budget.get(cost):
            return f"{who} has already used its {cost} this turn"
    elif " attacks " in lower:
        c = chars.get(who) or {}
        if not any(c.get(k) for k in ("melee", "ranged", "cantrip")):
            return f"{who} has nothing to attack with"
        if budget.get("action"):
            return f"{who} has already used its action this turn"
    elif " drinks " in lower:
        # A potion is a bonus action, and an empty pack is refused by the ghost.
        # Both are ordinary play, so skip quietly rather than announcing a drink
        # that will not happen.
        if budget.get("bonus"):
            return f"{who} has already used its bonus action this turn"
    elif lower.endswith("rages"):
        if budget.get("bonus"):
            return f"{who} has already used its bonus action this turn"
        # Rage lasts ten rounds, so a barbarian who raged last turn is still
        # raging and the ghost refuses a second one. Announcing it anyway makes
        # the demo look broken for something that is the rules working.
        conditions = {str(c).lower() for c in (chars.get(who) or {}).get("conditions") or []}
        if any("rag" in c for c in conditions):
            return f"{who} is already raging"
    elif " moves " in lower:
        if not budget.get("movement_left_ft"):
            return f"{who} has no movement left"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--turns", type=int, default=0, help="stop after N turns (0 = a full round)")
    ap.add_argument("--dry", action="store_true", help="print the script, touch nothing")
    ap.add_argument("--no-roll", action="store_true",
                    help="keep the initiative already on the board")
    ap.add_argument("--log", default=None, help="path for the JSONL event log")
    ap.add_argument("--no-reset", action="store_true",
                    help="start from the board as it stands, without repositioning")
    ap.add_argument("--no-flavour", action="store_true",
                    help="skip the cluster's descriptive narration")
    ap.add_argument("--keep-dm-auto", action="store_true",
                    help="let the ghost keep running the monsters (causes double turns)")
    args = ap.parse_args()

    load_env()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = Log(args.log or os.path.join(LOG_DIR, f"autoplay-{stamp}.jsonl"))
    watch = LockWatch(log)
    if not args.dry:
        watch.start()
    voice = Voice(log, watch)
    ghost = Ghost(log)
    cluster = Cluster(log)
    demo = Autoplay(log, voice, ghost, watch, cluster, args.dry,
                    flavour=not args.no_flavour)

    log.event("run_start", rounds=args.rounds, turns=args.turns, dry=args.dry,
              gateway=voice.base, voice=voice.voice, ghost=GHOST,
              cluster=cluster.url, flavour=demo.flavour)

    st = ghost.state()
    if not st and not args.dry:
        log.fault("GHOST_DOWN", f"no ghost on {GHOST}; start it first")
        log.summary()
        return 1

    try:
        if not args.keep_dm_auto:
            demo.take_sole_control()
        if not args.no_reset:
            reset_board(demo, ghost, log)
        if not args.no_roll:
            demo.beat("roll initiative")
            st = ghost.state()

        order_len = len(st.get("characters") or {}) or 7
        total = args.turns or order_len * args.rounds

        for i in range(total):
            st = ghost.state()
            who = st.get("turn_of")
            if not who:
                log.fault("NO_ACTIVE_TURN", "nobody is up; is combat active?")
                break
            log.turn(st.get("round"), who)

            for step in plan(who, st):
                spoken, command = step[0], step[1]
                alts = step[2] if len(step) > 2 else None

                st = ghost.state()  # budget moves within the turn
                why = preflight(command, who, st, log)
                if why is not None:
                    log.warn("SKIPPED", f"{command!r}: {why}")
                    continue
                demo.beat(spoken, command, alternatives=alts)

            if i < total - 1:
                before = ghost.state().get("turn_of")
                demo.beat("next turn")
                after = ghost.state().get("turn_of")
                if not args.dry and after == before:
                    log.fault("TURN_DID_NOT_ADVANCE",
                              f"still {after}'s turn after 'next turn'")
    except KeyboardInterrupt:
        log.fault("INTERRUPTED", "stopped by hand")
    finally:
        if not args.keep_dm_auto:
            demo.return_control()
        if not args.dry:
            watch.stop()
            ghost_time = sum(s["seconds"] for s in watch.segments if s["owner"] == "ghost")
            ours = sum(s["seconds"] for s in watch.segments if s["owner"] == "autoplay")
            print(f"\n  speech: {ours:.0f}s spoken by autoplay, "
                  f"{ghost_time:.0f}s by the ghost, "
                  f"{len(watch.segments)} segments, none concurrent by construction")
            log.event("speech_totals", autoplay=round(ours, 1), ghost=round(ghost_time, 1),
                      segments=len(watch.segments))
        log.summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
