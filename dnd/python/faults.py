"""Fault logging, narration timing and flavour narration for the voice loop.

Everything here was learned the hard way in `autoplay.py`, which drives the same
ghost with scripted commands instead of a microphone. Four things it turned up
apply just as much to the live loop:

* **Failures need names.** "It didn't work" has a dozen causes -- the tunnel is
  down, the console is restarting, the model will not load, the action was
  already spent -- and they need different fixes. Every one gets a stable code,
  printed and appended to a JSONL file, and counted in a summary.

* **A refusal is not a fault.** A wall in the way or an action already used is
  the rules working. A traceback is not. Reporting them the same way trains you
  to ignore both.

* **The ghost narrates on its own schedule**, from a background task, and it
  takes anywhere from two to twenty seconds. Carrying on before it has finished
  is what makes two voices overlap -- and on a live microphone it is worse than
  untidy, because the speaker's own narration goes back into the mic and can
  trip the wake word.

* **The mechanical read-out is not narration.** "freak takes 11, down to 2" is
  the result, not the story. One short sentence from the cluster turns it into
  something a table wants to listen to, and it costs no wall-clock at all if it
  is fetched while the ghost is still reading the numbers out.

Stdlib only, on purpose: this is imported by the voice loop, which already
carries heavy dependencies, and by anything else that talks to the ghost.
"""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import Counter

# The same path speak.py and the ghost's voice/tts.py lock. The path is the
# contract between the three processes; whoever holds it owns the speaker.
AUDIO_LOCK_PATH = "/tmp/dnd-audio.lock"

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

NARRATION_START_TIMEOUT = float(os.getenv("VOICE_NARRATION_START", "30"))
NARRATION_END_TIMEOUT = float(os.getenv("VOICE_NARRATION_END", "180"))


# ---------------------------------------------------------------- fault log


class Log:
    """Console output, a JSONL event stream, and a tally of what went wrong."""

    def __init__(self, path: str | None = None) -> None:
        self.t0 = time.monotonic()
        self.counts: Counter = Counter()
        self.fh = None
        if path is None:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = os.path.join(LOG_DIR, f"voice-{stamp}.jsonl")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.fh = open(path, "a", buffering=1)
            self.path = path
        except OSError as e:
            print(f"[voice] cannot open the event log ({e}); console only")
            self.path = None

    def _write(self, kind: str, **fields) -> None:
        if self.fh is not None:
            rec = {"t": round(time.monotonic() - self.t0, 3), "kind": kind, **fields}
            self.fh.write(json.dumps(rec) + "\n")

    def event(self, kind: str, **fields) -> None:
        self._write(kind, **fields)

    def info(self, text: str, **fields) -> None:
        print(f"      \033[90m{text}\033[0m")
        self._write("info", text=text, **fields)

    def fault(self, code: str, detail: str, **fields) -> None:
        """Something is broken and wants fixing."""
        self.counts[code] += 1
        print(f"      \033[31m[{code}]\033[0m {detail}")
        self._write("fault", code=code, detail=detail, **fields)

    def warn(self, code: str, detail: str, **fields) -> None:
        """Expected play, or a recovered blip -- counted, not alarming."""
        self.counts[code] += 1
        print(f"      \033[33m[{code}]\033[0m {detail}")
        self._write("fault", code=code, detail=detail, benign=True, **fields)

    def summary(self) -> None:
        print("\n\033[1m— fault summary —\033[0m")
        if not self.counts:
            print("  clean session: no faults recorded")
        for code, n in self.counts.most_common():
            print(f"  {n:3}x  {code}")
        self._write("summary", counts=dict(self.counts))
        if self.fh is not None:
            print(f"  events: {self.path}")
            self.fh.close()
            self.fh = None


# ------------------------------------------------------- refusal taxonomy

# Why the ghost said no, read off the sentence it said no with. Order matters:
# the first match wins, so the specific patterns come before the loose ones.
# "has no " used to be in here and quietly filed "has no movement left" as a
# missing potion -- a classifier has to be as specific as the message it reads.
REFUSAL_CODES = [
    ("that went wrong", "GHOST_INTERNAL_ERROR"),
    ("no line of sight", "REFUSED_NO_SIGHT"),
    ("not in reach", "REFUSED_NOT_IN_REACH"),
    ("has already used its", "REFUSED_NO_BUDGET"),
    ("no level", "REFUSED_NO_SLOT"),
    ("is not carrying", "REFUSED_NO_ITEM"),
    ("no movement left", "REFUSED_NO_MOVEMENT"),
    ("is already raging", "REFUSED_ALREADY_ON"),
    ("who is acting", "REFUSED_UNPARSED"),
    ("i heard", "REFUSED_UNPARSED"),
]

# A refusal that is the rules working, not a defect. Everything else gets
# reported as a fault so it stands out.
BENIGN_REFUSALS = {
    "REFUSED_NO_SIGHT", "REFUSED_NOT_IN_REACH", "REFUSED_NO_BUDGET",
    "REFUSED_NO_SLOT", "REFUSED_NO_ITEM", "REFUSED_NO_MOVEMENT",
    "REFUSED_ALREADY_ON",
}


def classify_refusal(lines) -> str:
    joined = " ".join(str(l).lower() for l in (lines or []))
    for needle, code in REFUSAL_CODES:
        if needle in joined:
            return code
    return "REFUSED_OTHER"


def report_outcome(log: Log, command: str, entry: dict) -> str | None:
    """Log one command's result. Returns the refusal code, or None if it stood."""
    lines = [str(l) for l in (entry.get("lines") or [])]
    log.event("command", command=command, ok=bool(entry.get("ok")), lines=lines)
    if entry.get("ok"):
        return None
    code = classify_refusal(lines)
    detail = f"{command!r}: {lines[0] if lines else 'no reason given'}"
    (log.warn if code in BENIGN_REFUSALS else log.fault)(code, detail)
    return code


# --------------------------------------------------- who is holding the speaker


def lock_busy() -> bool:
    """Is somebody speaking through the shared speaker right now?"""
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


def wait_for_narration(log: Log, expected: bool = True) -> None:
    """Block until the ghost has finished reading this outcome out.

    Two phases, because the ghost synthesises *before* it takes the lock: wait
    for it to start, then wait for it to finish. A flat sleep cannot do this --
    local Kokoro takes two seconds for a short line and twenty for a long one.

    On the live loop this is also what keeps the microphone out of the way. Going
    back to listening while the speaker is still talking feeds the narration
    straight back into the mic.
    """
    started = False
    deadline = time.monotonic() + NARRATION_START_TIMEOUT
    while time.monotonic() < deadline:
        if lock_busy():
            started = True
            break
        time.sleep(0.1)

    if not started:
        if expected:
            log.fault(
                "NARRATION_NEVER_STARTED",
                f"nothing was spoken within {NARRATION_START_TIMEOUT:.0f}s of an "
                "outcome that had lines; the next line may talk over it",
            )
        return

    deadline = time.monotonic() + NARRATION_END_TIMEOUT
    while time.monotonic() < deadline:
        if not lock_busy():
            time.sleep(0.4)  # let the sink drain
            return
        time.sleep(0.1)
    log.fault("NARRATION_TIMEOUT",
              f"the ghost was still speaking after {NARRATION_END_TIMEOUT:.0f}s")


# --------------------------------------------------------- flavour narration

# Commands that move the game along without anybody doing anything in the
# fiction. Handing these to the narrator produces invented events: "next turn"
# came back as "Weirdo unleashes a spectral force that envelops their foe",
# which no dice had rolled and nobody had asked for.
_BOOKKEEPING = (
    "roll initiative", "next turn", "previous turn", "end turn", "clear initiative",
    "end combat", "long rest", "short rest", "dm auto", "teleport", "clear ",
    "set round", "undo", "target ",
)


def is_bookkeeping(command: str) -> bool:
    lowered = (command or "").strip().lower()
    return any(lowered.startswith(p) or lowered == p.strip() for p in _BOOKKEEPING)


def roles(command: str):
    """(actor, target) out of a command line, for the flavour prompt.

    Crude on purpose -- in this grammar the actor is always the first word and
    the target follows the last preposition. Enough to stop a small model
    narrating the victim as the aggressor, which is what it does otherwise:
    "freak attacks cat" came back as the cat doing the attacking.
    """
    words = (command or "").strip().split()
    if not words:
        return "the character", None
    actor = words[0]
    lowered = [w.lower() for w in words]
    for prep in ("on", "from", "to", "at"):
        if prep in lowered:
            tail = words[len(lowered) - 1 - lowered[::-1].index(prep) + 1:]
            if tail:
                return actor, " ".join(tail)
    if len(words) >= 3:
        return actor, words[-1]
    return actor, None


class Flavour:
    """One vivid sentence per action, from the cluster.

    Fetched on a worker thread while the ghost is still reading out the
    mechanical result, so the round trip costs nothing: by the time the ghost
    stops talking the sentence is already waiting.

    A sentence of prose does not need a 70b, and the big one is frequently
    unloadable -- the cluster's GPUs are shared and `llama3.3:70b` (42 GB)
    answers "CUDA error: out of memory" whenever somebody else has them. The
    chain is tried in order and the first model that answers is kept.
    """

    FALLBACKS = ["mistral:7b-instruct", "qwen3:8b", "llama3.1:8b", "llama3.2:3b"]

    def __init__(self, log: Log, url: str | None = None) -> None:
        self.log = log
        self.url = (url or os.getenv("cluster_url") or "").strip() or None
        preferred = os.getenv("VOICE_FLAVOUR_MODEL")
        self.candidates = [preferred] if preferred else list(self.FALLBACKS)
        self.model = self.candidates[0]
        self.enabled = bool(self.url) and os.getenv("VOICE_FLAVOUR", "1").lower() not in (
            "0", "false", "no"
        )

    def _once(self, model: str, prompt: str, timeout: float, temperature: float):
        """(text, try_the_next_model)."""
        body = json.dumps({
            "model": model, "stream": False, "think": False,
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
            if "out of memory" in detail.lower() or "cuda error" in detail.lower():
                self.log.warn("CLUSTER_MODEL_OOM", f"{model} will not load")
                return None, True
            self.log.fault("CLUSTER_HTTP_ERROR", f"HTTP {e.code} from {model}")
            return None, False
        except Exception as e:  # noqa: BLE001 - a quiet table beats a dead loop
            self.log.fault("CLUSTER_UNREACHABLE", f"{type(e).__name__}: {e}")
            return None, False

        if isinstance(payload, dict) and payload.get("error"):
            detail = str(payload["error"])[:200]
            retry = "out of memory" in detail.lower() or "cuda error" in detail.lower()
            (self.log.warn if retry else self.log.fault)(
                "CLUSTER_MODEL_OOM" if retry else "CLUSTER_ERROR", f"{model}: {detail[:80]}")
            return None, retry

        text = str((payload.get("message") or {}).get("content") or "").strip()
        if not text:
            self.log.fault("CLUSTER_EMPTY", f"{model} replied with nothing")
            return None, True
        return text, False

    def chat(self, prompt: str, timeout: float = 25, temperature: float = 0.85):
        if not self.enabled:
            return None
        order = [self.model] + [m for m in self.candidates if m != self.model]
        for model in order:
            text, retryable = self._once(model, prompt, timeout, temperature)
            if text is not None:
                self.model = model
                return text
            if not retryable:
                return None
        self.log.fault("CLUSTER_ALL_MODELS_FAILED", "no flavour narration this session")
        self.enabled = False
        return None

    def sentence(self, command: str, lines) -> str | None:
        if not self.enabled or not lines or is_bookkeeping(command):
            return None
        actor, target = roles(command)
        who = f"The one acting is {actor}."
        if target and target != actor:
            who += f" It is happening to {target}. {target} is NOT the one acting."
        prompt = (
            "You are the dungeon master narrating a Dungeons & Dragons fight out loud.\n"
            f"The player declared: {command}\n"
            f"{who}\n"
            f"The rules resolved it as: {' '.join(str(l) for l in lines)}\n\n"
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
        text = self.chat(prompt)
        if text is None:
            return None
        first = text.replace("\n", " ").strip().strip('"')
        for stop in (". ", "! ", "? "):
            if stop in first:
                first = first[: first.index(stop) + 1]
                break
        if len(first) > 240:
            first = first[:240].rsplit(" ", 1)[0] + "."
        return first or None

    def start(self, command: str, lines):
        """Kick the sentence off now; call `.finish()` on what this returns."""
        if not self.enabled or not lines or is_bookkeeping(command):
            return None
        box: dict = {}

        def fetch():
            box["text"] = self.sentence(command, lines)

        worker = threading.Thread(target=fetch, daemon=True, name="flavour")
        worker.start()
        return (worker, box)

    def finish(self, handle, timeout: float = 30) -> str | None:
        if handle is None:
            return None
        worker, box = handle
        worker.join(timeout=timeout)
        if worker.is_alive():
            self.log.warn("FLAVOUR_SLOW", "the cluster did not answer in time")
            return None
        return box.get("text")
