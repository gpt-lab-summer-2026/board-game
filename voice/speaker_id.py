"""Speaker enrollment + identification via a single whole-clip embedding.

Replaces the earlier diarization approach for telling players apart: instead
of running a full segmentation+clustering pipeline over an ongoing
conversation, each player enrolls once at game start (one short clip -> one
embedding vector), and later a short wake-word clip is compared against the
enrolled set by cosine similarity. No running transcript, no timestamps --
just "whose voice was that."
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .config import SpeakerIdConfig

log = logging.getLogger(__name__)

EMBED_SAMPLE_RATE = 16000

# Same models/ convention as tts.py's Kokoro files: a local copy checked into place by
# hand, so the mic pipeline never needs a network round-trip once it's there. This is
# just the checkpoint pyannote/wespeaker-voxceleb-resnet34-LM downloads to on first run
# (see hf_hub_download's cache) -- copy pytorch_model.bin here from
# ~/.cache/huggingface/hub/models--pyannote--wespeaker-voxceleb-resnet34-LM/blobs/ (the
# ~26MB one) to skip the Hub entirely on every later run.
LOCAL_CHECKPOINT_PATH = Path(__file__).parent / "models" / "wespeaker-voxceleb-resnet34-LM" / "pytorch_model.bin"


class SpeakerEmbedder:
    def __init__(self, cfg: SpeakerIdConfig):
        import torch  # lazy: heavy dependency
        from pyannote.audio import Inference, Model

        self._torch = torch

        # Model.from_pretrained treats an existing file path as a fully local load --
        # no huggingface_hub call at all in that branch, so no network, no login, no
        # dependence on the Hub being reachable. Falls back to the Hub only if this
        # project's local copy hasn't been placed yet.
        if LOCAL_CHECKPOINT_PATH.exists():
            log.info("Loading speaker embedding model from local copy (%s)...", LOCAL_CHECKPOINT_PATH)
            checkpoint = str(LOCAL_CHECKPOINT_PATH)
        else:
            log.info("Loading speaker embedding model from Hugging Face Hub (no local copy at %s)...",
                     LOCAL_CHECKPOINT_PATH)
            # pyannote/wespeaker-voxceleb-resnet34-LM is a public, ungated repo -- confirmed by
            # downloading it anonymously (token=False) directly. cfg.hf_token defaults to None,
            # which tells huggingface_hub "send a cached login token if one exists, but don't
            # require one" -- the correct default for a model that doesn't need auth at all.
            # Passing True instead forces "a token must exist," which fails even for a public
            # repo if you've never run `hf auth login`.
            checkpoint = "pyannote/wespeaker-voxceleb-resnet34-LM"

        try:
            model = Model.from_pretrained(checkpoint, token=cfg.hf_token)
        except Exception as e:
            raise RuntimeError(
                "Couldn't load the pyannote embedding model -- pass an explicit token via "
                f"--hf-token / HF_TOKEN if this is a network/rate-limit issue. Original error: {e}"
            ) from e
        model.to(torch.device(cfg.device))
        # window="whole" gives ONE vector for the whole clip, instead of the diarization
        # pipeline's per-sliding-window embeddings meant for clustering a long recording --
        # that's what made the old approach slow (~37s for a 20s clip); this is ~0.3s for
        # a 2s clip, because it's exactly the one forward pass we actually need.
        self._inference = Inference(model, window="whole")

    def embed(self, audio: np.ndarray, sample_rate: int = EMBED_SAMPLE_RATE) -> np.ndarray:
        """audio: mono int16 or float32 [-1, 1] samples at `sample_rate`."""
        if audio.dtype == np.int16:
            audio = audio.astype("float32") / 32768.0
        waveform = {
            "waveform": self._torch.from_numpy(audio[None, :].astype("float32")),
            "sample_rate": sample_rate,
        }
        return self._inference(waveform)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@dataclass
class VoiceRoster:
    """Enrolled players for one game session. In-memory only -- a session is
    short-lived, so there's no need to persist embeddings across processes yet."""

    threshold: float = 0.5
    _voices: dict = field(default_factory=dict)

    def enroll(self, name: str, embedding: np.ndarray) -> None:
        self._voices[name] = embedding

    def identify(self, embedding: np.ndarray) -> tuple[Optional[str], float]:
        """Best-matching enrolled name and its similarity score. Returns (None, score)
        if the best match doesn't clear `threshold` (an unenrolled voice, or noise).

        This is open-set 1:N identification -- it picks a winner across every enrolled
        voice. With two similar-sounding players, their embeddings can sit close enough
        together that one of them just never wins the argmax, no matter who actually
        spoke. For turn-gating specifically, prefer verify() below: we already know who
        SHOULD be talking, so there's no need to make similar voices compete at all.
        """
        if not self._voices:
            return None, 0.0
        scores = {name: cosine_similarity(embedding, ref) for name, ref in self._voices.items()}
        best_name = max(scores, key=scores.get)
        best_score = scores[best_name]
        return (best_name, best_score) if best_score >= self.threshold else (None, best_score)

    def verify(self, name: str, embedding: np.ndarray) -> tuple[bool, float]:
        """1:1 check -- does `embedding` match specifically `name`'s enrolled voice?

        Unlike identify(), this never compares against anyone else's voice, so two
        players who sound similar don't compete for the same match: each is judged
        only against their own reference, which is exactly what turn-gating needs
        ("does this sound like the person whose turn it is") rather than "who does
        this sound like most, out of everyone."
        """
        ref = self._voices.get(name)
        if ref is None:
            return False, 0.0
        score = cosine_similarity(embedding, ref)
        return score >= self.threshold, score
