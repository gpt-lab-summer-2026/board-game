"""Config objects for the wake-word + speaker-ID turn-gating harness."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioConfig:
    capture_rate: int = 48000      # the mic's native rate -- requesting 16k directly from ALSA
                                    # is unreliable on hardware that doesn't support it natively
    sample_rate: int = 16000       # what openWakeWord and pyannote both expect; audio.resample
                                    # converts every captured chunk down to this before it's used
    channels: int = 1
    device: Optional[int] = None   # sounddevice input index; None = system default


@dataclass
class WakeWordConfig:
    model: str = "hey_jarvis"      # one of openwakeword's bundled pretrained models (no download
                                    # needed); swap for a custom-trained word once one exists
    threshold: float = 0.5         # score above which a frame counts as a detection


@dataclass
class SpeakerIdConfig:
    device: str = "cpu"
    hf_token: Optional[str] = None     # required -- pyannote models are gated on HF
    match_threshold: float = 0.5       # cosine similarity below this = "unrecognized voice"
