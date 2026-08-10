
"""
Usage:
    python3 -m voice.play_game
"""
from __future__ import annotations

import argparse
import logging
import time
from collections import deque

from .config import AudioConfig, SttConfig, WakeWordConfig
from .listen import (
    CHUNK_SAMPLES,
    AudioCapture,
    CommandTranscriber,
    UiServer,
    WakeWordDetector,
    wait_for_wake_word,
)

ID_BUFFER_SECONDS = 2.0
NAME_SECONDS = 8.0
# See test_turn_gate.py's identical constant for why 6s.
COMMAND_SECONDS = 6.0
# How many follow-up commands a turn accepts without repeating the wake word --
# e.g. "hey jarvis, roll the dice" then, unprompted, "move to Hakametsä". Capped
# rather than unlimited so a player who's fallen quiet for good eventually goes
# back to needing the wake word, instead of the mic silently listening forever.
MAX_FOLLOWUPS = 2


def run_setup(capture, detector, transcriber, ui, rolling) -> None:

    print('Listening for players, say player and number and your name -- '
          'for example, "player 1, Alice, player 2, Bob" (or just "I\'m Alice" one at a '
          'time). Once everyone has, say "hey jarvis, begin".')
    while ui.get_current_player() is None:
        print("[setup] waiting for the wake word...")
        ui.broadcast_status("waiting_for_wake_word")
        wait_for_wake_word(capture, detector, rolling)
        rolling.clear()
        print("[setup] wake word detected")

        ui.broadcast_status("recording")
        print(f"[setup] recording for {NAME_SECONDS:.0f}s...")
        follow_up = capture.record_seconds(NAME_SECONDS)
        print(f"[setup] recorded {len(follow_up)} samples, transcribing...")
        ui.broadcast_status("transcribing")
        spoken = transcriber.transcribe(follow_up)
        print(f"[setup] heard: {spoken!r} -- relaying to the browser to interpret")
        ui.broadcast_transcript("", spoken, phase="setup")
    print(f"[setup] done -- browser reports current player is {ui.get_current_player()!r}")


def run_game(capture, detector, transcriber, ui, rolling) -> None:
    """Most turns are two utterances -- "roll the dice", then once the number's
    known, "move to X" -- and repeating the wake word for both was exactly the
    friction players complained about. So after a wake-worded command, this
    stays in a short follow-up window (see MAX_FOLLOWUPS) that keeps listening
    without it, and only falls back to requiring the wake word again once a
    follow-up comes back empty, the turn changes, or the cap is used up.

    This doesn't turn the mic fully always-on: outside that brief post-command
    window, the wake word is still required, same as before.
    """
    print("[game] started. Listening for turns.")
    last_logged_expected = None
    while True:
        expected = ui.get_current_player()
        if expected is None:
            # Shouldn't normally happen once the browser has started the game --
            # guards a restart/race rather than crashing on an empty roster.
            time.sleep(0.2)
            continue
        if expected != last_logged_expected:
            print(f"[game] waiting for {expected!r} to say the wake word...")
            last_logged_expected = expected

        ui.broadcast_status("waiting_for_wake_word", player=expected)
        wait_for_wake_word(capture, detector, rolling)
        rolling.clear()
        # No speaker-ID: whoever just said the wake word is trusted to be `expected`,
        # since that's who the browser says is up.
        print(f"[game] wake word detected -- trusting it's {expected!r} (no speaker-ID)")

        followups_left = MAX_FOLLOWUPS
        while True:
            ui.set_message(f"Listening to {expected}...")
            ui.broadcast_status("recording", player=expected)
            print(f"[game] recording command for {COMMAND_SECONDS:.0f}s...")
            command_audio = capture.record_seconds(COMMAND_SECONDS)
            print(f"[game] recorded {len(command_audio)} samples, transcribing...")
            ui.broadcast_status("transcribing", player=expected)
            transcript = transcriber.transcribe(command_audio)
            print(f"[game] {expected} said: {transcript!r}")
            ui.broadcast_transcript(expected, transcript, phase="playing")

            if not transcript.strip():
                print("[game] heard nothing further -- back to requiring the wake word")
                break
            followups_left -= 1
            if followups_left <= 0:
                print("[game] follow-up limit reached -- back to requiring the wake word")
                break
            if ui.get_current_player() != expected:
                print("[game] turn changed -- back to requiring the wake word")
                break
            print(f"[game] listening for a follow-up ({followups_left} left) -- "
                  f"no wake word needed...")
            ui.broadcast_status("listening_for_followup", player=expected)
        print("[game] broadcasted to browser, waiting for its next current_player update...")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wake-word", default="hey_jarvis", help="bundled openWakeWord model name")
    p.add_argument("--threshold", type=float, default=0.5, help="wake word detection threshold")
    p.add_argument("--ui-port", type=int, default=8765, help="local web UI port")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    print(f"[init] wake word={args.wake_word!r} threshold={args.threshold}")

    audio_cfg = AudioConfig()
    capture = AudioCapture(audio_cfg)  # logs which capture backend (pw-record/ffmpeg) it picked
    transcriber = CommandTranscriber(SttConfig())

    ui = UiServer(port=args.ui_port)
    ui.start()  # logs the exact status/websocket addresses -- check these against
                # vite.config.ts's proxy targets if the browser never connects

    detector = WakeWordDetector(WakeWordConfig(model=args.wake_word, threshold=args.threshold))
    buffer_chunks = max(1, int(ID_BUFFER_SECONDS * audio_cfg.sample_rate / CHUNK_SAMPLES))
    rolling: deque = deque(maxlen=buffer_chunks)

    run_setup(capture, detector, transcriber, ui, rolling)
    run_game(capture, detector, transcriber, ui, rolling)


if __name__ == "__main__":
    main()
