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

import numpy as np

from .audio import AudioCapture
from .config import AudioConfig, SpeakerIdConfig, WakeWordConfig
from .speaker_id import SpeakerEmbedder, VoiceRoster
from .wakeword import CHUNK_SAMPLES, WakeWordDetector

ENROLL_SECONDS = 4.0
# Rolling buffer used as the identification clip on a wake-word hit -- long enough to
# contain the whole wake phrase (openWakeWord fires partway through/after it's said).
ID_BUFFER_SECONDS = 2.0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--players", required=True, help="comma-separated player names, e.g. Alice,Bob")
    p.add_argument("--input-device", type=int, default=None, help="sounddevice input index")
    p.add_argument("--wake-word", default="hey_jarvis", help="bundled openWakeWord model name")
    p.add_argument("--threshold", type=float, default=0.5, help="wake word detection threshold")
    p.add_argument("--match-threshold", type=float, default=0.5, help="cosine similarity match threshold")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN"), help="or set the HF_TOKEN env var")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    players = [p.strip() for p in args.players.split(",") if p.strip()]
    if len(players) < 2:
        raise SystemExit("need at least 2 players, e.g. --players Alice,Bob")

    audio_cfg = AudioConfig(device=args.input_device)
    capture = AudioCapture(audio_cfg)
    embedder = SpeakerEmbedder(SpeakerIdConfig(hf_token=args.hf_token, match_threshold=args.match_threshold))
    roster = VoiceRoster(threshold=args.match_threshold)

    for name in players:
        input(f"\n{name}: press Enter, then talk for {ENROLL_SECONDS:.0f}s to enroll your voice...")
        sample = capture.record_seconds(ENROLL_SECONDS)
        roster.enroll(name, embedder.embed(sample))
        print(f"Enrolled {name}.")

    detector = WakeWordDetector(WakeWordConfig(model=args.wake_word, threshold=args.threshold))
    buffer_chunks = max(1, int(ID_BUFFER_SECONDS * audio_cfg.sample_rate / CHUNK_SAMPLES))
    rolling: deque = deque(maxlen=buffer_chunks)

    turn_idx = 0
    print(f'\nListening for "{args.wake_word}"... it\'s {players[turn_idx]}\'s turn. (Ctrl+C to stop)')
    for chunk in capture.stream_16k_chunks(CHUNK_SAMPLES):
        rolling.append(chunk)
        event = detector.process_chunk(chunk)
        if event is None:
            continue

        clip = np.concatenate(list(rolling))
        name, score = roster.identify(embedder.embed(clip))
        expected = players[turn_idx]

        if name is None:
            print(f"Wake word heard (score {event.score:.2f}) but voice not recognized "
                  f"(best match {score:.2f}) -- ignoring.")
        elif name == expected:
            print(f"Wake word heard from {name} (match {score:.2f}) -- it was their turn. ACTIVATED.")
            turn_idx = (turn_idx + 1) % len(players)
            print(f"Now it's {players[turn_idx]}'s turn.")
        else:
            print(f"Wake word heard from {name} (match {score:.2f}), but it's {expected}'s turn -- ignoring.")


if __name__ == "__main__":
    main()
