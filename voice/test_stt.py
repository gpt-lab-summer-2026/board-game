"""Manual test: what does the STT step actually transcribe?

Isolates faster-whisper from the rest of the pipeline (no wake word, no
speaker-ID) so a bad transcript can be pinned on either the audio capture or
the model itself rather than guessed at: records a clip, saves it as a WAV
you can play back and listen to, then prints what faster-whisper heard --
once with VAD filtering (the normal in-game setting) and once without, since
a transcript that's empty or missing words but sounds fine in the WAV usually
means the VAD filter misjudged real speech as silence and discarded it.

Usage:
    python -m voice.test_stt
    python -m voice.test_stt --seconds 10 --model small.en
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .audio import AudioCapture, save_wav
from .config import AudioConfig, SttConfig
from .stt import CommandTranscriber


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seconds", type=float, default=6.0, help="how long to record each take")
    p.add_argument("--model", default=None, help="override the faster-whisper model name "
                                                    "(default: SttConfig's distil-small.en)")
    p.add_argument("--language", default=None, help="override the STT language (default: en)")
    p.add_argument("--save-dir", default="voice/recordings",
                   help="where each take's WAV is saved for listening back")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    audio_cfg = AudioConfig()
    capture = AudioCapture(audio_cfg)

    stt_cfg = SttConfig()
    if args.model:
        stt_cfg.model = args.model
    if args.language:
        stt_cfg.language = args.language
    transcriber = CommandTranscriber(stt_cfg)
    print(f"STT model: {stt_cfg.model} ({stt_cfg.device}/{stt_cfg.compute_type}), language={stt_cfg.language}")

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nRecording {args.seconds:.0f}s per take. Ctrl+C to stop.")
    take = 0
    while True:
        take += 1
        input(f"\n[{take}] Press Enter, then speak for {args.seconds:.0f}s...")
        audio = capture.record_seconds(args.seconds)

        wav_path = save_dir / f"take-{take:03d}.wav"
        save_wav(str(wav_path), audio, audio_cfg.sample_rate)
        print(f"  Saved: {wav_path}  (play it back to check the capture itself sounds right)")

        with_vad = transcriber.transcribe(audio, vad_filter=True)
        print(f'  Transcript (VAD on,  in-game setting): "{with_vad}"')

        without_vad = transcriber.transcribe(audio, vad_filter=False)
        if without_vad != with_vad:
            print(f'  Transcript (VAD off, for comparison): "{without_vad}"')
            print("  -- these differ: the VAD filter is changing what gets transcribed. If the "
                  "VAD-off version has real words the VAD-on one is missing, the wake-word clip "
                  "or command window is likely too quiet/fast for the filter -- try speaking a "
                  "beat louder or right after the wake word, or lower this further by adjusting "
                  "faster-whisper's vad_parameters in stt.py.")

        if not with_vad and not without_vad:
            print("  -- both transcripts are empty. Check the saved WAV: if there's clearly "
                  "audible speech in it, the model/language/audio format is the problem, not "
                  "VAD. If the WAV is silent or full of noise, the mic capture itself "
                  "(voice/audio.py) is what to look at next.")


if __name__ == "__main__":
    main()
