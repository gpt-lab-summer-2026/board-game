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
    #
    # check with `ffmpeg -f avfoundation -list_devices true -i ""` and set this to match.
    mac_input_device: str = "1"


@dataclass
class WakeWordConfig:
    model: str = "hey_jarvis"      # one of openwakeword's bundled pretrained models (no download
                                    # needed); swap for a custom-trained word once one exists
    threshold: float = 0.5         # score above which a frame counts as a detection


@dataclass
class SpeakerIdConfig:
    device: str = "cpu"
    # None = send a cached `hf auth login` token if one exists, but don't require one --
    # the wespeaker embedding model is a public, ungated repo. Pass a string to force an
    # explicit token instead (e.g. to dodge anonymous-request rate limits).
    hf_token: object = None
    match_threshold: float = 0.5       # cosine similarity below this = "unrecognized voice"


@dataclass
class SttConfig:
    model: str = "distil-small.en"  # faster-whisper arch name
    device: str = "cpu"
    compute_type: str = "int8"      # int8 keeps this usable on a Pi's CPU
    language: str = "en"
    # Vocabulary bias for whisper -- e.g. the board's Finnish place names, which an
    # English-only model wouldn't otherwise favor. A mitigation, not a fix: it won't
    # always land on an unfamiliar name exactly. Exact resolution now happens on the
    # React side (src/llm/names.ts) against the real board.
    initial_prompt: str | None = None
