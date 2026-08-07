"""Live dice reader: point the camera at a phone showing a die face.

    python -m vision.test_dice                    # window + saved frames
    python -m vision.test_dice --no-window        # headless, frames only
    python -m vision.test_dice --whole-frame      # skip YOLO, read the full view

YOLO locates the phone (COCO's `cell phone` class) so the pip counter only ever
looks at the screen, not at a whiteboard full of round clutter. The value is
only announced once it has held still for a few frames -- see StableReading.

Keys in the window: q or Esc quits, s saves the current frame immediately.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2

from .camera import Camera, CameraConfig
from .dice import StableReading, annotate as annotate_pips, read_dice

log = logging.getLogger(__name__)

# COCO has no die, but it does have the thing holding it. Ordered by preference:
# a real `cell phone` always wins, `remote` is only here because a phone held
# edge-on is regularly mistaken for one.
#
# `tv`/`laptop` are deliberately absent. In this room they match the projected
# board -- a big bright rectangle covered in round route markers, which is
# exactly what a pip counter will happily miscount as a die. Observed: with
# `tv` enabled the reader announced a 2 off the projection with no phone in
# frame. Pass --extra-labels to opt them back in.
PHONE_LABELS: tuple[str, ...] = ("cell phone", "remote")


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--device", type=int, default=0)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument(
        "--whole-frame",
        action="store_true",
        help="don't use YOLO; look for pips across the entire frame",
    )
    p.add_argument(
        "--yolo-every",
        type=int,
        default=3,
        help="run YOLO every Nth frame and reuse its box in between "
        "(YOLO is ~200ms, pip counting is ~2ms)",
    )
    p.add_argument(
        "--confidence", type=float, default=0.25,
        help="YOLO confidence floor for the phone",
    )
    p.add_argument(
        "--extra-labels",
        default="",
        help="comma-separated extra COCO labels to accept as the phone "
        "(e.g. tv,laptop) -- risky near a projected board, see PHONE_LABELS",
    )
    p.add_argument(
        "--stable-frames", type=int, default=4,
        help="frames a value must persist before it's announced",
    )
    p.add_argument("--no-window", action="store_true", help="headless")
    p.add_argument(
        "--save-dir",
        default="/tmp/dice_frames",
        help="annotated frames are written here",
    )
    p.add_argument(
        "--save-every", type=int, default=15,
        help="save every Nth frame (0 disables periodic saving)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    labels = PHONE_LABELS + tuple(
        label.strip()
        for label in args.extra_labels.split(",")
        if label.strip()
    )

    detector = None
    if not args.whole_frame:
        from .objects import ObjectDetector

        detector = ObjectDetector(confidence=args.confidence)
        print(f"Looking for: {', '.join(labels)}")

    stable = StableReading(required=args.stable_frames)
    phone_box: tuple[int, int, int, int] | None = None
    frame_no = 0
    saved = 0
    read_failures = 0
    last_announced: int | None = None

    print(
        "Reading dice. "
        + ("Window: q/Esc quit, s save. " if not args.no_window else "")
        + f"Frames -> {save_dir}"
    )

    with Camera(
        CameraConfig(
            device=args.device, width=args.width, height=args.height
        )
    ) as cam:
        try:
            while True:
                try:
                    frame = cam.read()
                    read_failures = 0
                except RuntimeError as err:
                    # The camera has re-enumerated mid-session before (it moved
                    # USB ports). Reopening recovers it; only give up if it
                    # really is gone.
                    read_failures += 1
                    if read_failures > 5:
                        raise
                    log.warning(
                        "camera read failed (%s), reopening [%d/5]",
                        err, read_failures,
                    )
                    time.sleep(1.0)
                    try:
                        cam.reopen()
                    except Exception:  # noqa: BLE001 - retry on the next pass
                        log.debug("reopen failed", exc_info=True)
                    continue
                frame_no += 1
                height, width = frame.shape[:2]

                # Locate the phone. YOLO is the slow part, so it runs
                # periodically and its box is reused on the frames between.
                if detector is not None and frame_no % args.yolo_every == 1:
                    candidates = [
                        d
                        for d in detector.detect(frame)
                        if d.label in labels
                    ]
                    # Rank by label preference first, confidence only to break
                    # ties within a label -- so a 40%-sure phone still beats a
                    # 90%-sure monitor.
                    best = min(
                        candidates,
                        key=lambda d: (
                            labels.index(d.label),
                            -d.confidence,
                        ),
                        default=None,
                    )
                    if best is not None:
                        x1, y1, x2, y2 = (int(v) for v in best.box)
                        # A little margin: YOLO's box can clip the screen edge,
                        # and a clipped pip is a miscount.
                        pad = 8
                        phone_box = (
                            max(x1 - pad, 0),
                            max(y1 - pad, 0),
                            min(x2 + pad, width),
                            min(y2 + pad, height),
                        )
                    else:
                        phone_box = None

                if args.whole_frame:
                    region = frame
                    origin = (0, 0)
                elif phone_box is not None:
                    x1, y1, x2, y2 = phone_box
                    region = frame[y1:y2, x1:x2]
                    origin = (x1, y1)
                else:
                    region = None
                    origin = (0, 0)

                started = time.monotonic()
                reading = read_dice(region) if region is not None and region.size else None
                took = (time.monotonic() - started) * 1000
                value = stable.update(reading.value if reading else None)

                if value != last_announced:
                    if value is None:
                        print("  -- no die in view")
                    else:
                        print(f"  dice roll: {value}")
                    last_announced = value

                # ---- draw ----
                shown = frame.copy()
                if phone_box is not None:
                    x1, y1, x2, y2 = phone_box
                    cv2.rectangle(shown, (x1, y1), (x2, y2), (255, 128, 0), 2)
                    cv2.putText(
                        shown, "phone", (x1, max(y1 - 8, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 128, 0), 2,
                    )
                annotate_pips(shown, reading, origin)

                label = (
                    f"DICE: {value}" if value is not None
                    else (f"reading… ({reading.value})" if reading else "no die")
                )
                cv2.putText(
                    shown, label, (16, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                    (0, 255, 0) if value is not None else (0, 165, 255), 3,
                )
                cv2.putText(
                    shown,
                    f"{took:.0f}ms pips | frame {frame_no}"
                    + ("" if detector else " | whole-frame"),
                    (16, height - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1,
                )

                if args.save_every and frame_no % args.save_every == 0:
                    out = save_dir / f"frame_{frame_no:05d}.jpg"
                    cv2.imwrite(str(out), shown)
                    saved += 1

                if not args.no_window:
                    cv2.imshow("dice", shown)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
                    if key == ord("s"):
                        out = save_dir / f"manual_{frame_no:05d}.jpg"
                        cv2.imwrite(str(out), shown)
                        saved += 1
                        print(f"  saved {out}")
        except KeyboardInterrupt:
            pass
        finally:
            if not args.no_window:
                cv2.destroyAllWindows()

    print(f"\nstopped after {frame_no} frames; {saved} saved to {save_dir}")


if __name__ == "__main__":
    main()
