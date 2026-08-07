"""Real voice-driven game loop: wake word -> speaker-ID turn gate -> faster-whisper
-> browser (React + gemma3 own move/roll/turn logic from here on).

Two phases:

SETUP -- no roster yet, so every wake-word activation is checked with an open-set
roster.identify() rather than a verify() against an expected speaker (there's no
"expected" until players exist). An unrecognized voice enrolls as a new player,
using one utterance ("hey jarvis, I'm Alice") for both the embedding AND the
name -- see turn_gate.py's enroll_players for the alternative, repeat-based
enrollment this trades some voiceprint robustness for. An already-enrolled voice
speaking again is relayed as-is; the browser treats "start"/"begin" in that text
as the cue to move on (see src/voice/transcript.ts and src/App.tsx).

PLAYING -- once the browser calls onBeginGame, it pushes {"type": "current_player",
"player": ...} over the same websocket (see ui_server.py), which is this phase's
signal to start, and its only source of whose turn it is thereafter. Unlike
test_turn_gate.py's demo loop, this file keeps NO local turn counter: once "roll
the dice" and "move to X" become separate utterances, only the browser (which
runs the actual turn logic) knows when a turn really ends, so asking the browser
is the only way this stays correct.

Usage:
    python -m voice.play_game
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from collections import deque

from .audio import AudioCapture
from .config import AudioConfig, SpeakerIdConfig, SttConfig, WakeWordConfig
from .speaker_id import SpeakerEmbedder, VoiceRoster
from .stt import CommandTranscriber
from .turn_gate import ID_BUFFER_SECONDS, wait_for_activation, wait_for_wake_word
from .ui_server import UiServer
from .wakeword import CHUNK_SAMPLES, WakeWordDetector

# How long to record after the wake word during setup, to capture a spoken name
# ("hey jarvis, I'm Alice") or a meta-command from an already-enrolled voice
# ("hey jarvis, let's begin"). Shorter than COMMAND_SECONDS -- both are short.
NAME_SECONDS = 3.0
# See test_turn_gate.py's identical constant for why 6s.
COMMAND_SECONDS = 6.0

_NAME_FILLERS = ("hey jarvis", "hey jarviss", "my name is", "i'm ", "im ", "this is", "it's ")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wake-word", default="hey_jarvis", help="bundled openWakeWord model name")
    p.add_argument("--threshold", type=float, default=0.5, help="wake word detection threshold")
    p.add_argument("--match-threshold", type=float, default=0.5, help="cosine similarity match threshold")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"),
                    help="the embedding model is a public repo, so this is normally unneeded; "
                         "set HF_TOKEN to force an explicit token (e.g. to avoid rate limits)")
    p.add_argument("--ui-port", type=int, default=8765, help="local web UI port")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def clean_name(spoken: str) -> str:
    """'hey jarvis, I'm Alice' -> 'Alice': strips the filler faster-whisper transcribes
    around a name. Crude on purpose -- same "stub now, LLM later" precedent as
    game_stub.py; gemma3 could do this more robustly later without changing the
    rest of this file."""
    text = spoken.strip()
    lowered = text.lower()
    for filler in _NAME_FILLERS:
        idx = lowered.find(filler)
        if idx != -1:
            text = text[idx + len(filler):]
            lowered = text.lower()
    cleaned = text.strip(" .,!?'\"").title()
    return cleaned or "Player"


def run_setup(capture, detector, embedder, transcriber, roster, ui, rolling) -> None:
    """Collect players by voice until the browser signals the game has begun (see
    the module docstring). Returns once ui.get_current_player() is no longer None
    -- including if that happens via the browser's typed/clicked setup form
    instead of voice, since a mixed flow (some players typed, some spoke) is
    perfectly fine here: whoever never enrolled by voice just won't be recognized
    for voice turns later and can fall back to typing, same as always.
    """
    print(f'Listening for "{detector.cfg.model}"... say it plus your name to join '
          f'(e.g. "hey jarvis, I\'m Alice"). Once everyone has, an already-joined '
          f'voice can say "begin".')
    while ui.get_current_player() is None:
        ui.broadcast_status("waiting_for_wake_word")
        id_clip = wait_for_wake_word(capture, detector, rolling)
        rolling.clear()
        embedding = embedder.embed(id_clip)

        ui.broadcast_status("recording")
        print(f"Recording for {NAME_SECONDS:.0f}s...")
        follow_up = capture.record_seconds(NAME_SECONDS)
        ui.broadcast_status("transcribing")
        spoken = transcriber.transcribe(follow_up)

        identified, score = roster.identify(embedding)
        if identified is None:
            player_name = clean_name(spoken)
            roster.enroll(player_name, embedding)
            print(f"Enrolled new player {player_name!r} (heard: {spoken!r})")
            ui.broadcast_transcript(player_name, spoken, phase="setup", event="player_joined")
        else:
            print(f"{identified} (match {score:.2f}) said: {spoken!r}")
            ui.broadcast_transcript(identified, spoken, phase="setup", event="player_spoke")


def run_game(capture, detector, embedder, roster, transcriber, ui, rolling) -> None:
    print("Game started -- listening for turns.")
    while True:
        expected = ui.get_current_player()
        if expected is None:
            # Shouldn't normally happen once the browser has started the game --
            # guards a restart/race rather than crashing on an empty roster.
            time.sleep(0.2)
            continue

        ui.broadcast_status("waiting_for_wake_word", player=expected)
        name, score = wait_for_activation(capture, detector, embedder, roster, rolling,
                                           players=[expected], turn_idx=0)
        rolling.clear()
        ui.set_message(f"Listening to {name}...")
        ui.broadcast_status("recording", player=name)

        print(f"Recording command for {COMMAND_SECONDS:.0f}s...")
        command_audio = capture.record_seconds(COMMAND_SECONDS)
        ui.broadcast_status("transcribing", player=name)
        transcript = transcriber.transcribe(command_audio)
        print(f"{name}: {transcript!r}")
        ui.broadcast_transcript(name, transcript, phase="playing")


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    audio_cfg = AudioConfig()
    capture = AudioCapture(audio_cfg)
    embedder = SpeakerEmbedder(SpeakerIdConfig(hf_token=args.hf_token, match_threshold=args.match_threshold))
    transcriber = CommandTranscriber(SttConfig())
    roster = VoiceRoster(threshold=args.match_threshold)

    ui = UiServer(port=args.ui_port)
    ui.start()
    print(f"Board UI: http://<this-pi's-ip>:5173/  (status API on :{args.ui_port})")

    detector = WakeWordDetector(WakeWordConfig(model=args.wake_word, threshold=args.threshold))
    buffer_chunks = max(1, int(ID_BUFFER_SECONDS * audio_cfg.sample_rate / CHUNK_SAMPLES))
    rolling: deque = deque(maxlen=buffer_chunks)

    run_setup(capture, detector, embedder, transcriber, roster, ui, rolling)
    run_game(capture, detector, embedder, roster, transcriber, ui, rolling)


if __name__ == "__main__":
    main()
