"""Reading the outcome of a turn out loud.

The last stage of the pipeline: `... -> ui functions -> slm turn processing ->
kokoro tts`. The executor already produces prose rather than a data structure,
so narration is mostly a matter of getting it to a speaker without stalling the
event loop.

Kokoro synthesis is CPU-bound and takes appreciably longer than a socket
round-trip, so it runs in a worker thread. It is also entirely optional: the
voice stack lives in a different tree with heavy dependencies (onnxruntime,
phonemizer) that need not be installed to drive the board from the console.
Import failure is a shrug, not an error.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# The voice package sits beside PlanarAlly rather than inside it.
VOICE_ROOT = Path(__file__).resolve().parents[2]


class Narrator:
    """Speaks lines, one at a time, without blocking the ghost."""

    def __init__(self, speaker) -> None:
        self._speaker = speaker
        # Serialised: two overlapping voices reporting different halves of a
        # turn is worse than a slight delay.
        self._lock = asyncio.Lock()

    async def __call__(self, text: str) -> None:
        if not text.strip():
            return
        async with self._lock:
            await asyncio.to_thread(self._speaker.speak, text)


def try_build(voice: str = "af_aoede") -> Narrator | None:
    """A Narrator, or None if the voice stack isn't available here.

    `GHOST_MUTE=1` returns None deliberately. The voice loop in ../python
    narrates its own results too, so with both running every outcome is read out
    twice, over itself. That file is not ours to edit, so this is the lever from
    this side: mute the ghost and let the voice loop be the single narrator.
    The console and the action panel then go quiet, which is the cost.
    """
    if os.environ.get("GHOST_MUTE", "").strip().lower() in {"1", "true", "yes"}:
        log.info("GHOST_MUTE set; the console will stay silent")
        return None
    if str(VOICE_ROOT) not in sys.path:
        sys.path.insert(0, str(VOICE_ROOT))
    try:
        from voice.tts import KokoroSpeaker  # noqa: PLC0415 - optional, heavy
    except Exception as e:  # noqa: BLE001
        log.info("no TTS (%s); the console will stay silent", e)
        return None

    try:
        return Narrator(KokoroSpeaker(voice=voice))
    except Exception as e:  # noqa: BLE001 - missing model files are expected
        log.info("TTS unavailable (%s); the console will stay silent", e)
        return None
