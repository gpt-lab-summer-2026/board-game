"""Placeholder command handler, used only by test_turn_gate.py.

Real gemma3 integration happened -- just not here. It lives in the browser
(src/llm/intent.ts's resolveMoveIntent, reached from play_game.py's voice
websocket bridge instead of a direct Python call) because the browser is what
holds the actual board/game state a move needs to be resolved against. This
stub exists only so test_turn_gate.py -- which exercises the mic pipeline on
its own, with no browser involved -- has something to feed its response outlet
(tts.py speaking it, ui_server.py displaying it) with representative text.
"""
from __future__ import annotations


def process_command(transcript: str, current_player: str, next_player: str) -> str:
    """Crude keyword matching over the transcript, standing in for what gemma3
    will eventually decide from the same text. Returns the line that gets both
    spoken (Kokoro) and shown (text box)."""
    text = transcript.lower()

    if "money" in text or "afford" in text:
        return f"Sorry {current_player}, you don't have enough money for that."
    if "ambiguous" in text or ("up" in text and "down" in text):
        return f"That move is ambiguous, {current_player} -- would you like to go up or down?"
    if "can't" in text or "cant" in text or "cannot" in text:
        return f"You can't move there, {current_player}."

    return f"{current_player}'s turn processed. Next turn is {next_player}."
