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
