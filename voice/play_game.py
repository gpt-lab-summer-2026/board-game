"""Real game entry point: whisper -> pyannote -> gemma3 -> kokoro.

Ties together wake-word + speaker verification (turn_gate.py) for turn
gating, transcribes the actual command, asks gemma3 (via llama-server) to
parse it into a structured action, applies that action against the
authoritative GameEngine, and speaks + displays the outcome.

Square effects and the city-square layout are placeholder data (see
game_engine.placeholder_square_types) pending the user's real 7-piece
layout -- swap that in via GameEngine's square_types param once it exists.

Usage:
    python -m voice.play_game --players Alice,Bob
"""
from __future__ import annotations

import argparse
import logging
import os
from collections import deque

from .audio import AudioCapture
from .board import BoardGraph
from .config import AudioConfig, LlmConfig, SpeakerIdConfig, SttConfig, WakeWordConfig
from .game_engine import GameEngine, MoveOutcome, placeholder_square_types
from .llm import CLARIFY_TEXT, IntentParser, LlamaServerProcess
from .speaker_id import SpeakerEmbedder
from .stt import CommandTranscriber
from .tts import KokoroSpeaker
from .turn_gate import ID_BUFFER_SECONDS, enroll_players, wait_for_activation
from .ui_server import UiServer
from .wakeword import CHUNK_SAMPLES, WakeWordDetector

log = logging.getLogger(__name__)

ENROLL_REPEATS = 3
# How long to record the actual command after a valid wake word -- "dice roll is 4,
# moving towards south" fits comfortably; this stands in for the camera noticing a
# piece has moved, since there's no camera yet.
COMMAND_SECONDS = 6.0
DEFAULT_START_CITY = "keskustori"


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--players", required=True, help="comma-separated player names, e.g. Alice,Bob")
    p.add_argument("--board", default="cities.json", help="path to the board graph JSON")
    p.add_argument("--start-city", default=DEFAULT_START_CITY, help="starting city / return point to win")
    p.add_argument("--seed", type=int, default=None, help="random seed for placeholder gem placement")
    p.add_argument("--wake-word", default="hey_jarvis", help="bundled openWakeWord model name")
    p.add_argument("--threshold", type=float, default=0.5, help="wake word detection threshold")
    p.add_argument("--match-threshold", type=float, default=0.5, help="cosine similarity match threshold")
    p.add_argument("--hf-token", default=os.environ.get("HF_TOKEN") or True,
                    help="defaults to whatever `hf auth login` cached; set HF_TOKEN to override")
    p.add_argument("--ui-port", type=int, default=8765, help="local web UI port")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def outcome_to_text(outcome: MoveOutcome, next_player: str) -> str:
    """Deterministic response text -- not LLM-generated. Once the game engine
    applies an action its effects are fully determined, so a second LLM call
    here would only add latency (we're already ~25-30s deep per turn -- see
    voice/llm.py) and a fresh chance to misstate a number/name that's already
    known for certain."""
    parts = [f"{outcome.player} moved to {outcome.destination}."]
    if outcome.money_delta > 0:
        parts.append(f"Found {outcome.money_delta} money.")
    elif outcome.money_delta < 0:
        parts.append(f"Lost {-outcome.money_delta} money to a robber.")
    if outcome.picked_up_gem:
        parts.append("That's the winning gem! Get it back to the start to win.")
    if outcome.won:
        parts.append(f"{outcome.player} wins the game!")
    else:
        parts.append(f"Next turn: {next_player}.")
    return " ".join(parts)


def handle_command(intent_parser: IntentParser, transcriber: CommandTranscriber, capture,
                    speaker: KokoroSpeaker, ui: UiServer, engine: GameEngine,
                    max_clarification_rounds: int) -> MoveOutcome | None:
    """Records + transcribes a command, resolves it via gemma3 (with up to
    max_clarification_rounds follow-up rounds if unclear), and applies it.
    Returns the MoveOutcome, or None if the move was abandoned/wasn't a move."""
    current_city = engine.current_player.position
    hints = engine.plausible_destinations()
    prior_attempt = None

    for round_num in range(max_clarification_rounds + 1):
        print(f"Recording command for {COMMAND_SECONDS:.0f}s...")
        audio = capture.record_seconds(COMMAND_SECONDS)
        transcript = transcriber.transcribe(audio)
        print(f"Command: {transcript!r}")

        ui.set_message("Thinking...")
        intent = intent_parser.parse(transcript, current_city, hints, prior_attempt=prior_attempt)

        if intent.action == "move":
            return engine.apply_move(intent.destination, intent.mode, intent.dice_value)

        if intent.action == "other":
            message = "Got it, but I can only handle moves for now."
            ui.set_message(message)
            speaker.speak(message)
            return None

        # action == "unclear" -- ask a clarifying question (speak + show), try again
        if round_num < max_clarification_rounds:
            question = CLARIFY_TEXT.get(intent.unclear_reason, CLARIFY_TEXT["no_match"])
            print(f"Unclear ({intent.unclear_reason}): {question}")
            ui.set_message(question)
            speaker.speak(question)
            prior_attempt = transcript
        else:
            message = "Let's skip this for now -- try your move again next turn."
            ui.set_message(message)
            speaker.speak(message)

    return None


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    players = [p.strip() for p in args.players.split(",") if p.strip()]
    if len(players) < 2:
        raise SystemExit("need at least 2 players, e.g. --players Alice,Bob")

    board = BoardGraph.load(args.board)
    if args.start_city not in board.cities:
        raise SystemExit(f"--start-city {args.start_city!r} is not on the board")
    square_types = placeholder_square_types(board, args.start_city, seed=args.seed)
    engine = GameEngine(board, players, args.start_city, square_types)

    audio_cfg = AudioConfig()
    capture = AudioCapture(audio_cfg)
    embedder = SpeakerEmbedder(SpeakerIdConfig(hf_token=args.hf_token, match_threshold=args.match_threshold))
    stt_prompt = "Place names: " + ", ".join(board.cities)
    transcriber = CommandTranscriber(SttConfig(initial_prompt=stt_prompt))
    speaker = KokoroSpeaker()

    ui = UiServer(port=args.ui_port)
    ui.start()
    print(f"Text box: http://<this-pi's-ip>:{args.ui_port}/")

    roster = enroll_players(capture, embedder, players, args.wake_word, ENROLL_REPEATS,
                             args.match_threshold)

    detector = WakeWordDetector(WakeWordConfig(model=args.wake_word, threshold=args.threshold))
    buffer_chunks = max(1, int(ID_BUFFER_SECONDS * audio_cfg.sample_rate / CHUNK_SAMPLES))
    rolling: deque = deque(maxlen=buffer_chunks)

    llm_cfg = LlmConfig()
    with LlamaServerProcess(llm_cfg) as llama:
        intent_parser = IntentParser(llm_cfg, llama.base_url, board)

        print(f'\nListening for "{args.wake_word}"... it\'s {players[0]}\'s turn. (Ctrl+C to stop)')
        while True:
            turn_idx = players.index(engine.current_player.name)
            name, _score = wait_for_activation(capture, detector, embedder, roster,
                                                rolling, players, turn_idx)
            rolling.clear()  # stale pre-activation audio shouldn't bleed into the next wait

            ui.set_message(f"Listening to {name}...")
            outcome = handle_command(intent_parser, transcriber, capture, speaker, ui,
                                      engine, llm_cfg.max_clarification_rounds)

            if outcome is None:
                continue  # no move applied -- same player's turn again

            next_player = engine.current_player.name
            response = outcome_to_text(outcome, next_player)
            ui.set_message(response, {"type": "square_landed", "square_type": outcome.square_type})
            speaker.speak(response)
            print(f"Now it's {next_player}'s turn." if not outcome.won else "Game over.")

            if outcome.won:
                break


if __name__ == "__main__":
    main()
