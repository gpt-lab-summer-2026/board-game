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
    mac_input_device: str = "3"


@dataclass
class WakeWordConfig:
    model: str = "hey_jarvis"      # one of openwakeword's bundled pretrained models (no download
                                    # needed); swap for a custom-trained word once one exists
    threshold: float = 0.5         # score above which a frame counts as a detection


@dataclass
class SpeakerIdConfig:
    device: str = "cpu"
    hf_token: object = None
    match_threshold: float = 0.5       # cosine similarity below this = "unrecognized voice"


@dataclass
class SttConfig:
    # distil-small.en (the previous default) is English-ONLY -- distil-whisper has no
    # multilingual variant at all, so it had zero chance of transcribing the board's
    # Finnish place names correctly, no matter how it was prompted. "small" is the
    # smallest *multilingual* whisper size; if it's too slow on the Pi, "base" is the
    # next multilingual step down, still far better than an English-only model here.
    model: str = "small"  # faster-whisper arch name
    device: str = "cpu"
    compute_type: str = "int8"      # int8 keeps this usable on a Pi's CPU
    # Commands are framed in English ("heading for X", "roll the dice") with a Finnish
    # place name embedded, not whole sentences in Finnish -- forcing language="fi" would
    # instead mangle the English framing. initial_prompt below is the real lever for the
    # embedded Finnish proper nouns: it biases the model's vocabulary without changing
    # which language it decodes in.
    language: str = "en"

    # The board's actual place names (src/game/board2.json), so the model has SOME prior
    # on what a Finnish place name said mid-sentence should sound like, instead of forcing
    # it to fall back on English phonetics for words it's never going to get exactly right
    # anyway. A mitigation, not a fix -- exact resolution still happens against the real
    # board in src/llm/names.ts's matchCityName, which this exists to feed better input to.
    initial_prompt: str | None = (
        "Places on the board: Annala, Finlayson, Hakametsä, Hervannan vesitorni, "
        "Iidesjärvi, Kalevan kirkko, Kalevan prisma, Kapina, Kaukajärvi, Kauppi, "
        "Keskustori, Koskipuisto, Laukontori, Makkarajärvi, Mini autokauppa helvetti, "
        "Perensaari, Rantaperkiö, Ratina, Rautatieasema, Sorsapuisto, Suolijärvi, "
        "Tammelan tori, Tammerkoski, Tampere talo, Tulli, Turtola, Vapriikki, "
        "Viikinsaari, Wäinölät, Yliopisto Hervannan kampus, Yliopisto keskusta kampus, "
        "arboretum."
    )
