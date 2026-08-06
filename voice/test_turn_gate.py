"""Manual test: wake word + speaker-ID turn gating.

Enrolls each player's voice at the start of a game, then listens continuously
for the wake word. On detection, identifies who said it from the enrolled
voices and checks it against whichever player's turn it currently is (a
simple round-robin here -- there's no real game state to hook into yet).

This replaces the earlier full-diarization test: we don't need a running
transcript or word timestamps, just "was that the right player's voice,
yes or no" on the short wake-word clip itself.

Usage:
    python -m voice.test_turn_gate --players Alice,Bob
"""
from __future__ import annotations

import argparse
import logging
import os
from collections import deque

from .audio import AudioCapture
from .config import AudioConfig, SpeakerIdConfig, SttConfig, WakeWordConfig
from .game_stub import process_command
from .speaker_id import SpeakerEmbedder, VoiceRoster
from .stt import CommandTranscriber
from .tts import KokoroSpeaker
from .turn_gate import ID_BUFFER_SECONDS, enroll_players, wait_for_activation
from .ui_server import UiServer
from .wakeword import CHUNK_SAMPLES, WakeWordDetector

ENROLL_REPEATS = 3
# How long to record the actual command after a valid wake word -- "dice roll is 4,
# moving towards south" fits comfortably; this stands in for the camera noticing a
# piece has moved, since there's no camera yet.
COMMAND_SECONDS = 6.0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--players", required=True, help="comma-separated player names, e.g. Alice,Bob")
    p.add_argument("--wake-word", default="hey_jarvis", help="bundled openWakeWord model name")
    p.add_argument("--threshold", type=float, default=0.5, help="wake word detection threshold")
    p.add_argument("--match-threshold", type=float, default=0.5, help="cosine similarity match threshold")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN") or True,
                    help="defaults to whatever `hf auth login` cached; set HF_TOKEN to override")
    p.add_argument("--ui-port", type=int, default=8765, help="local web UI port")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    players = [p.strip() for p in args.players.split(",") if p.strip()]
    if len(players) < 2:
        raise SystemExit("need at least 2 players, e.g. --players Alice,Bob")

    audio_cfg = AudioConfig()
    capture = AudioCapture(audio_cfg)
    embedder = SpeakerEmbedder(SpeakerIdConfig(hf_token=args.hf_token, match_threshold=args.match_threshold))
    transcriber = CommandTranscriber(SttConfig())
    speaker = KokoroSpeaker()

    ui = UiServer(port=args.ui_port)
    ui.start()
    print(f"Text box: http://<this-pi's-ip>:{args.ui_port}/")

    roster = enroll_players(capture, embedder, players, args.wake_word, ENROLL_REPEATS,
                             args.match_threshold)

    detector = WakeWordDetector(WakeWordConfig(model=args.wake_word, threshold=args.threshold))
    buffer_chunks = max(1, int(ID_BUFFER_SECONDS * audio_cfg.sample_rate / CHUNK_SAMPLES))
    rolling: deque = deque(maxlen=buffer_chunks)

    turn_idx = 0
    print(f'\nListening for "{args.wake_word}"... it\'s {players[turn_idx]}\'s turn. (Ctrl+C to stop)')
    while True:
        name, _score = wait_for_activation(capture, detector, embedder, roster, rolling, players, turn_idx)
        rolling.clear()  # stale pre-activation audio shouldn't bleed into the next wait

        ui.set_message(f"Listening to {name}...")
        print(f"Recording command for {COMMAND_SECONDS:.0f}s...")
        command_audio = capture.record_seconds(COMMAND_SECONDS)
        transcript = transcriber.transcribe(command_audio)
        print(f"Command: {transcript!r}")

        next_player = players[(turn_idx + 1) % len(players)]
        response = process_command(transcript, current_player=name, next_player=next_player)
        ui.set_message(response)
        speaker.speak(response)

        turn_idx = (turn_idx + 1) % len(players)
        print(f"Now it's {players[turn_idx]}'s turn.")


if __name__ == "__main__":
    main()
