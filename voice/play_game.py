"""
Usage:
    python -m voice.play_game
"""
from __future__ import annotations

import argparse
import logging
import re
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
COMMAND_SECONDS = 6.0

_NAME_FILLERS = ("hey jarvis", "hey jarviss", "my name is", "i'm ", "im ", "this is", "it's ")
_BEGIN_RE = re.compile(r"\b(start|begin)\b", re.IGNORECASE)
_PLAYER_NUMBER = r"\d+|one|two|three|four|five|six|seven|eight|nine|ten"
_PLAYER_LIST_RE = re.compile(
    rf"player\s*(?:number\s*)?(?:{_PLAYER_NUMBER})\s*[:,\-]?\s*([a-z][a-z'\-]*)",
    re.IGNORECASE,
)

def clean_name(spoken: str) -> str:
    #'hey jarvis, I'm Alice' -> 'Alice'
    text = spoken.strip()
    lowered = text.lower()
    for filler in _NAME_FILLERS:
        idx = lowered.find(filler)
        if idx != -1:
            text = text[idx + len(filler):]
            lowered = text.lower()
    cleaned = text.strip(" .,!?'\"").title()
    return cleaned or "Player"


def parse_player_list(spoken: str) -> list[str]:
    # 'player 1: Alice, player 2, Bob' -> ['Alice', 'Bob']
    return [m.group(1).strip().title() for m in _PLAYER_LIST_RE.finditer(spoken)]


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
        print(f"[setup] heard: {spoken!r}")

        if _BEGIN_RE.search(spoken):
            print("[setup] that's a start/begin phrase -- relaying it for the browser to act on")
            ui.broadcast_transcript("", spoken, phase="setup", event="player_spoke")
            continue

        player_names = parse_player_list(spoken)
        if player_names:
            print(f"[setup] heard a player list: {player_names}")
        else:
            # Doesn't look like "player N: Name" at all -- treat the whole utterance
            # as one person introducing themselves, same as before this list syntax existed.
            player_names = [clean_name(spoken)]
            print(f"[setup] treating this as a single new player: {player_names[0]!r}")

        for player_name in player_names:
            ui.broadcast_transcript(player_name, spoken, phase="setup", event="player_joined")
    print(f"[setup] done -- browser reports current player is {ui.get_current_player()!r}")


def run_game(capture, detector, transcriber, ui, rolling) -> None:
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
        ui.set_message(f"Listening to {expected}...")
        ui.broadcast_status("recording", player=expected)

        print(f"[game] recording command for {COMMAND_SECONDS:.0f}s...")
        command_audio = capture.record_seconds(COMMAND_SECONDS)
        print(f"[game] recorded {len(command_audio)} samples, transcribing...")
        ui.broadcast_status("transcribing", player=expected)
        transcript = transcriber.transcribe(command_audio)
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
