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
from typing import Optional

import numpy as np

from .config import SpeakerIdConfig

log = logging.getLogger(__name__)

EMBED_SAMPLE_RATE = 16000


class SpeakerEmbedder:
    def __init__(self, cfg: SpeakerIdConfig):
        import torch  # lazy: heavy dependency
        from pyannote.audio import Inference, Model

        if not cfg.hf_token:
            raise ValueError(
                "SpeakerIdConfig.hf_token is required to fetch the pyannote embedding model. "
                "Create a read token at https://huggingface.co/settings/tokens (or run `hf auth "
                "login`), then pass it via --hf-token or HF_TOKEN."
            )

        self._torch = torch
        log.info("Loading speaker embedding model...")
        model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM", token=cfg.hf_token)
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
        if the best match doesn't clear `threshold` (an unenrolled voice, or noise)."""
        if not self._voices:
            return None, 0.0
        scores = {name: cosine_similarity(embedding, ref) for name, ref in self._voices.items()}
        best_name = max(scores, key=scores.get)
        best_score = scores[best_name]
        return (best_name, best_score) if best_score >= self.threshold else (None, best_score)
