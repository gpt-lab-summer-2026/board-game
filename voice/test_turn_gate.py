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
from .config import AudioConfig, SpeakerIdConfig, SttConfig, WakeWordConfig
from .game_stub import process_command
from .speaker_id import SpeakerEmbedder, VoiceRoster
from .stt import CommandTranscriber
from .tts import KokoroSpeaker
from .ui_server import UiServer
from .wakeword import CHUNK_SAMPLES, WakeWordDetector

# Enrollment records the wake word itself, repeated, rather than arbitrary free speech --
# a speaker embedding is somewhat content-dependent, and the only clip identification
# ever sees at runtime is the wake phrase, so enrolling on mismatched content (a sentence
# vs. two words) was making matches noisier than they needed to be. Repeating it a few
# times and averaging the embeddings smooths out per-utterance noise too.
ENROLL_REPEATS = 3
# Rolling buffer used as the identification clip on a wake-word hit -- long enough to
# contain the whole wake phrase (openWakeWord fires partway through/after it's said).
# Enrollment clips use this same length so they're directly comparable to it.
ID_BUFFER_SECONDS = 2.0
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


def wait_for_activation(capture, detector, embedder, roster, rolling, players, turn_idx):
    """Block until the current player says the wake word; returns (name, score).

    Verifies the clip against specifically the EXPECTED player (roster.verify),
    not an open-set "who does this sound most like" across everyone (roster.identify)
    -- with two similar-sounding players, identify()'s argmax lets one of them win
    every time regardless of who actually spoke, since it's a competition between
    voices rather than a check against the one voice that should be talking.

    Runs its own stream_16k_chunks() loop and returns out of it (rather than the
    caller looping chunk-by-chunk itself) so the mic stream is fully torn down
    before record_seconds() below opens a second one -- this hardware doesn't
    tolerate two simultaneous input streams (see audio.py/test_turn_gate history).
    """
    expected = players[turn_idx]
    for chunk in capture.stream_16k_chunks(CHUNK_SAMPLES):
        rolling.append(chunk)
        event = detector.process_chunk(chunk)
        if event is None:
            continue

        clip = np.concatenate(list(rolling))
        verified, score = roster.verify(expected, embedder.embed(clip))

        if not verified:
            print(f"Wake word heard (score {event.score:.2f}) but didn't match {expected}'s "
                  f"enrolled voice (similarity {score:.2f}) -- ignoring.")
            continue

        print(f"Wake word heard from {expected} (match {score:.2f}) -- ACTIVATED.")
        return expected, score


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
    roster = VoiceRoster(threshold=args.match_threshold)
    transcriber = CommandTranscriber(SttConfig())
    speaker = KokoroSpeaker()

    ui = UiServer(port=args.ui_port)
    ui.start()
    print(f"Text box: http://<this-pi's-ip>:{args.ui_port}/")

    spoken_wake_word = args.wake_word.replace("_", " ")
    for name in players:
        print(f'\n{name}: enroll by saying "{spoken_wake_word}" {ENROLL_REPEATS} times.')
        embeddings = []
        for i in range(ENROLL_REPEATS):
            input(f'  ({i + 1}/{ENROLL_REPEATS}) Press Enter, then say "{spoken_wake_word}"...')
            sample = capture.record_seconds(ID_BUFFER_SECONDS)
            embeddings.append(embedder.embed(sample))
        roster.enroll(name, np.mean(embeddings, axis=0))
        print(f"Enrolled {name}.")

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
