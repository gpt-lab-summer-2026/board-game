"""Config objects for the wake-word + speaker-ID turn-gating harness."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioConfig:
    capture_rate: int = 48000      # the mic's native rate -- requesting 16k directly from ALSA
                                    # is unreliable on hardware that doesn't support it natively
    sample_rate: int = 16000       # what openWakeWord and pyannote both expect; audio.resample
                                    # converts every captured chunk down to this before it's used
    channels: int = 1
    # No device index here (unlike the old sounddevice-based capture): pw-record targets
    # PipeWire's current default source. Change the input device with `wpctl set-default`
    # or `pw-record --target`, not through this config.


@dataclass
class WakeWordConfig:
    model: str = "hey_jarvis"      # one of openwakeword's bundled pretrained models (no download
                                    # needed); swap for a custom-trained word once one exists
    threshold: float = 0.5         # score above which a frame counts as a detection


@dataclass
class SpeakerIdConfig:
    device: str = "cpu"
    # True = use whatever `hf auth login` already cached (the normal case); pass a
    # string to override with an explicit token instead.
    hf_token: object = True
    match_threshold: float = 0.5       # cosine similarity below this = "unrecognized voice"


@dataclass
class SttConfig:
    model: str = "distil-small.en"  # faster-whisper arch name
    device: str = "cpu"
    compute_type: str = "int8"      # int8 keeps this usable on a Pi's CPU
    language: str = "en"
    # Vocabulary bias for whisper -- e.g. the board's Finnish place names, which an
    # English-only model wouldn't otherwise favor. Mitigation, not a fix: won't always
    # land on an unfamiliar name exactly; BoardGraph.closest_match() is the backstop.
    initial_prompt: str | None = None


@dataclass
class LlmConfig:
    server_binary: str = "llama.cpp/build/bin/llama-server"
    model_path: str = "models/gemma-3-4b-it-q4_k_m.gguf"
    host: str = "127.0.0.1"
    port: int = 8091                  # distinct from llama-server's own default (8080) and ui_server's (8765)
    ctx_size: int = 4096
    threads: int = 4
    startup_timeout_s: float = 120.0  # first load of a 2.3GB q4 gguf off SD/eMMC can be slow
    # Measured on this Pi: ~25-31s per call even on a cache hit (prompt caching barely
    # helps in practice here -- see voice/llm.py's IntentParser docstring). 30s was the
    # original estimate-based default and turned out to be too tight, causing spurious
    # "llm_request_failed" clarification loops on legitimately-slow-but-successful calls.
    request_timeout_s: float = 60.0
    max_tokens: int = 96              # generation ceiling for the structured JSON reply
    temperature: float = 0.15         # low: grammar already constrains the space, want the best pick not variety
    top_p: float = 0.9
    max_clarification_rounds: int = 2
