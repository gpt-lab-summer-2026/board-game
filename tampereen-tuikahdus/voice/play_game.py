
"""
Usage:
    python3 -m voice.play_game
"""
from __future__ import annotations

import argparse
import logging
import time

from .config import AudioConfig, SttConfig, VadConfig, WakeWordConfig
from .listen import (
    AudioCapture,
    CommandTranscriber,
    UiServer,
    VoiceActivityDetector,
    WakeWordDetector,
    record_until_silence,
    wait_for_wake_word,
)

# After relaying a setup utterance to the browser, how long to give its LLM
# classification (e.g. recognizing "begin") a chance to land before going back to
# requiring the wake word. Without this, a player who immediately follows "begin"
# with their real first command -- before the browser's async classification has
# actually flipped current_player -- has that command captured here as just
# another setup utterance and silently dropped. Polling costs nothing: capture
# keeps one continuously-open stream (see main()), so audio isn't lost while waiting.
SETUP_SETTLE_POLLS = 20
SETUP_SETTLE_INTERVAL = 0.15


def run_setup(capture, detector, vad, vad_cfg, transcriber, ui) -> None:

    print('Listening for players, say player and number and your name -- '
          'for example, "player 1, Alice, player 2, Bob" (or just "I\'m Alice" one at a '
          'time). Once everyone has, say "hey jarvis, begin".')
    while ui.get_current_player() is None:
        print("[setup] waiting for the wake word...")
        ui.broadcast_status("waiting_for_wake_word")
        wait_for_wake_word(capture, detector)
        print("[setup] wake word detected")

        ui.broadcast_status("recording")
        print("[setup] recording (until silence)...")
        follow_up = record_until_silence(capture, vad, vad_cfg)
        print(f"[setup] recorded {len(follow_up)} samples, transcribing...")
        ui.broadcast_status("transcribing")
        spoken = transcriber.transcribe(follow_up)
        print(f"[setup] heard: {spoken!r} -- relaying to the browser to interpret")
        ui.broadcast_transcript("", spoken, phase="setup")

        for _ in range(SETUP_SETTLE_POLLS):
            if ui.get_current_player() is not None:
                break
            time.sleep(SETUP_SETTLE_INTERVAL)
    print(f"[setup] done -- browser reports current player is {ui.get_current_player()!r}")


def run_game(capture, detector, vad, vad_cfg, transcriber, ui) -> None:
    """Each turn: say the wake word, then say the command -- VAD ends the
    recording once the player actually stops talking (see record_until_silence),
    so "roll the dice" and "roll the dice and move towards X" both work in one
    breath. That made the old multi-recording follow-up window (repeatedly
    listening again without the wake word, hoping for a second utterance)
    unnecessary -- every turn is now exactly one wake-word-then-command cycle.
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
        wait_for_wake_word(capture, detector)
        # No speaker-ID: whoever just said the wake word is trusted to be `expected`,
        # since that's who the browser says is up.
        print(f"[game] wake word detected -- trusting it's {expected!r} (no speaker-ID)")

        ui.set_message(f"Listening to {expected}...")
        ui.broadcast_status("recording", player=expected)
        print("[game] recording (until silence)...")
        command_audio = record_until_silence(capture, vad, vad_cfg)
        print(f"[game] recorded {len(command_audio)} samples, transcribing...")
        ui.broadcast_status("transcribing", player=expected)
        transcript = transcriber.transcribe(command_audio)

        # Checked *before* broadcasting, not after: the turn can flip while the
        # recording above was in flight (e.g. an LLM-resolved action from an
        # earlier utterance finally landing), and attributing whatever was just
        # captured to a player whose turn already ended would be worse than
        # dropping it -- the browser would apply a stranger's speech as `expected`.
        if ui.get_current_player() != expected:
            print("[game] turn changed during recording -- discarding and "
                  "requiring the wake word again")
            continue

        print(f"[game] {expected} said: {transcript!r}")
        ui.broadcast_transcript(expected, transcript, phase="playing")
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
    # One continuously-open sounddevice stream for the whole run, shared by
    # wake-word detection and command recording alike -- see wait_for_wake_word/
    # record_until_silence in listen.py for why that matters (no dead-air gap).
    capture = AudioCapture(audio_cfg)
    transcriber = CommandTranscriber(SttConfig())
    vad = VoiceActivityDetector()
    vad_cfg = VadConfig()

    ui = UiServer(port=args.ui_port)
    ui.start()  # logs the exact status/websocket addresses -- check these against
                # vite.config.ts's proxy targets if the browser never connects

    detector = WakeWordDetector(WakeWordConfig(model=args.wake_word, threshold=args.threshold))

    run_setup(capture, detector, vad, vad_cfg, transcriber, ui)
    run_game(capture, detector, vad, vad_cfg, transcriber, ui)


if __name__ == "__main__":
    main()
