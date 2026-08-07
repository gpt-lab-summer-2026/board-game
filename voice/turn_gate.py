"""Shared wake-word + speaker-verification turn-gating helpers.

Used by both test_turn_gate.py (the lightweight wake+ID-only test) and
play_game.py (the real game loop) -- extracted here so neither duplicates
the other's enrollment/activation logic.
"""
from __future__ import annotations

import numpy as np

from .speaker_id import SpeakerEmbedder, VoiceRoster
from .wakeword import CHUNK_SAMPLES, WakeWordDetector

ID_BUFFER_SECONDS = 2.0  # length of both enrollment clips and the wake-word ID buffer


def enroll_players(capture, embedder: SpeakerEmbedder, players: list[str], wake_word: str,
                    repeats: int, match_threshold: float) -> VoiceRoster:
    """Enrolls each named player by having them say the wake word itself, repeated
    -- not arbitrary free speech. A speaker embedding is somewhat content-dependent,
    and the only clip identification ever sees at runtime is the wake phrase, so
    enrolling on mismatched content made matches noisier than necessary. Averaging
    `repeats` embeddings smooths out per-utterance noise too."""
    roster = VoiceRoster(threshold=match_threshold)
    spoken_wake_word = wake_word.replace("_", " ")

    for name in players:
        print(f'\n{name}: enroll by saying "{spoken_wake_word}" {repeats} times.')
        embeddings = []
        for i in range(repeats):
            input(f'  ({i + 1}/{repeats}) Press Enter, then say "{spoken_wake_word}"...')
            sample = capture.record_seconds(ID_BUFFER_SECONDS)
            embeddings.append(embedder.embed(sample))
        roster.enroll(name, np.mean(embeddings, axis=0))
        print(f"Enrolled {name}.")

    return roster


def wait_for_activation(capture, detector: WakeWordDetector, embedder: SpeakerEmbedder,
                         roster: VoiceRoster, rolling, players: list[str], turn_idx: int):
    """Block until the current player says the wake word; returns (name, score).

    Verifies the clip against specifically the EXPECTED player (roster.verify),
    not an open-set "who does this sound most like" across everyone (roster.identify)
    -- with two similar-sounding players, identify()'s argmax lets one of them win
    every time regardless of who actually spoke, since it's a competition between
    voices rather than a check against the one voice that should be talking.

    Runs its own stream_16k_chunks() loop and returns out of it (rather than the
    caller looping chunk-by-chunk itself) so the mic stream is fully torn down
    before record_seconds() opens a second one -- this hardware doesn't tolerate
    two simultaneous input streams (see audio.py's history).
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


def wait_for_wake_word(capture, detector: WakeWordDetector, rolling) -> np.ndarray:
    """Block until the wake word is heard, with no speaker check at all -- for
    play_game.py's voice-driven setup phase, where there's no "expected" player
    yet (the roster is still being built one enrollment at a time). Returns the
    same short ID-buffer clip wait_for_activation uses for its own embedding, so
    a caller can embed it the identical way and run roster.identify() on it.

    Same reasoning as wait_for_activation for running its own stream loop and
    returning out of it, rather than being called in a loop by the caller: this
    hardware doesn't tolerate two simultaneous input streams (see audio.py).
    """
    for chunk in capture.stream_16k_chunks(CHUNK_SAMPLES):
        rolling.append(chunk)
        event = detector.process_chunk(chunk)
        if event is None:
            continue
        return np.concatenate(list(rolling))
