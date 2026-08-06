"""Placeholder for the gemma3 command handler.

This is deliberately NOT the real thing -- gemma3 integration is a separate,
later step. It exists so the response outlet (tts.py speaking it, ui_server.py
displaying it) can be exercised end to end with representative text before
the real SLM is wired in. `process_command` should be a drop-in replacement
site for an actual gemma3 call: same inputs, same kind of short response string.
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
