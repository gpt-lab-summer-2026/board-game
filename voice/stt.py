"""Command transcription: plain faster-whisper, no alignment or diarization.

The turn-gating step (wakeword.py + speaker_id.py) already answered "whose
voice was that" from the wake-word clip alone -- this just needs the text of
the command that follows ("dice roll is 4, moving towards south"), so there's
no reason to carry whisperX's alignment/diarization machinery into this part
of the pipeline too.
"""
from __future__ import annotations

import logging

import numpy as np

from .config import SttConfig

log = logging.getLogger(__name__)


class CommandTranscriber:
    def __init__(self, cfg: SttConfig):
        from faster_whisper import WhisperModel  # lazy: heavy dependency

        self.cfg = cfg
        log.info("Loading whisper model %s (%s/%s)...", cfg.model, cfg.device, cfg.compute_type)
        self._model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)

    def transcribe(self, audio: np.ndarray, vad_filter: bool = True) -> str:
        """audio: mono float32 [-1, 1] samples at 16 kHz.

        vad_filter defaults on: record_seconds() always grabs a fixed window
        regardless of when the player actually starts/stops talking, so there's
        usually leading/trailing silence in it; without VAD, whisper transcribes
        that silence as part of the utterance too (prone to hallucinated words),
        instead of just skipping straight to the speech. Exposed as a parameter
        because that same filtering can also discard real speech it misjudges as
        non-speech -- see test_stt.py, which is built specifically to tell those
        two failure modes apart.
        """
        segments, _info = self._model.transcribe(audio, language=self.cfg.language, beam_size=5,
                                                   vad_filter=vad_filter,
                                                   initial_prompt=self.cfg.initial_prompt)
        print(segments)
        return " ".join(seg.text.strip() for seg in segments).strip()
