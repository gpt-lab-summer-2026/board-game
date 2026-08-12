"""Live dice reader: reads the die the game draws on the projected board.

    python -m vision.test_dice                       # window + saved frames
    python -m vision.test_dice --no-window           # headless, frames only
    python -m vision.test_dice --corner bottom-right # die drawn elsewhere
    python -m vision.test_dice --roi 0.6,0.05,0.98,0.4   # tighter than a quadrant
    python -m vision.test_dice --debug-roi           # dump the crop to inspect

The die is rendered by the game itself, so its location is known: find the
projected rectangle in the camera frame, take the named quadrant of it, and read
the die there. No YOLO -- it has no dice class and cannot read a value, and now
that the die sits at a known spot on the projection there is nothing left for an
object detector to find. Locating the projection by brightness costs ~10ms
against YOLO's ~200ms.

Resolution matters more than anything else here: the projected die is 24x21px at
720p, where its pips are ~2px and unreadable, and 65x58px at 2592x1944, where
they are not. Hence the default. --physical switches to the reader for a real
die (dark pips on a light face) instead.

Keys in the window: q or Esc quits, s saves the current frame immediately.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2

from .camera import Camera, CameraConfig
from .dice import (
    StableReading,
    annotate as annotate_pips,
    find_die,
    read_dice,
    read_projected_die,
)
from .projection import ProjectionTracker, annotate as annotate_projection

log = logging.getLogger(__name__)

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--device", type=int, default=0)
    # Measured against the projected die: at 1280x720 it lands 24x21px, whose
    # pips are ~2px of pale blue on white and are not reliably countable. At
    # 2592x1944 the same die is 65x58px and reads cleanly. 3840x2160 gains
    # almost nothing beyond that (72x64) for twice the pixels.
    p.add_argument("--width", type=int, default=2592)
    p.add_argument("--height", type=int, default=1944)
    p.add_argument(
        "--corner", choices=CORNERS, default="top-right",
        help="which quarter of the projection holds the die",
    )
    p.add_argument(
        "--roi",
        default=None,
        help="x1,y1,x2,y2 as fractions of the projection (overrides --corner) "
        "-- use when a whole quadrant picks up too much other UI",
    )
    p.add_argument(
        "--whole-frame",
        action="store_true",
        help="skip projection detection and read the entire camera frame",
    )
    p.add_argument(
        "--stable-frames", type=int, default=4,
        help="frames a value must persist before it's announced",
    )
    p.add_argument("--no-window", action="store_true", help="headless")
    p.add_argument(
        "--save-dir", default="/tmp/dice_frames",
        help="annotated frames are written here",
    )
    p.add_argument(
        "--save-every", type=int, default=15,
        help="save every Nth frame (0 disables periodic saving)",
    )
    p.add_argument(
        "--debug-roi", action="store_true",
        help="also save the raw crop the pip counter sees, for tuning",
    )
    p.add_argument(
        "--physical", action="store_true",
        help="read a real die (dark pips on a light face) instead of the one "
        "the game projects",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def parse_roi(text: str) -> tuple[float, float, float, float]:
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 4:
        raise SystemExit("--roi needs four comma-separated fractions")
    x1, y1, x2, y2 = parts
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise SystemExit("--roi fractions must satisfy 0 <= x1 < x2 <= 1 (same for y)")
    return x1, y1, x2, y2


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    roi = parse_roi(args.roi) if args.roi else None

    tracker = ProjectionTracker()
    stable = StableReading(required=args.stable_frames)
    frame_no = 0
    saved = 0
    read_failures = 0
    last_announced: int | None = None
    missing_projection = 0

    where = (
        "whole frame" if args.whole_frame
        else f"{args.corner} of the projection" if roi is None
        else f"ROI {roi} of the projection"
    )
    print(
        f"Reading dice from the {where}. "
        + ("Window: q/Esc quit, s save. " if not args.no_window else "")
        + f"Frames -> {save_dir}"
    )

    with Camera(
        CameraConfig(device=args.device, width=args.width, height=args.height)
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

                started = time.monotonic()
                projection = None
                if args.whole_frame:
                    box = (0, 0, width, height)
                else:
                    projection = tracker.update(frame)
                    if projection is None:
                        missing_projection += 1
                        if missing_projection in (1, 30):
                            print(
                                "  -- can't see the projection "
                                "(too dim, or out of frame?)"
                            )
                        box = None
                    else:
                        missing_projection = 0
                        if roi is None:
                            box = projection.quadrant(args.corner)
                        else:
                            fx1, fy1, fx2, fy2 = roi
                            box = (
                                projection.x1 + int(projection.width * fx1),
                                projection.y1 + int(projection.height * fy1),
                                projection.x1 + int(projection.width * fx2),
                                projection.y1 + int(projection.height * fy2),
                            )

                reading = None
                if box is not None:
                    x1, y1, x2, y2 = box
                    region = frame[y1:y2, x1:x2]
                    if region.size:
                        reading = (
                            read_dice(region) if args.physical
                            else read_projected_die(region)
                        )
                        if args.debug_roi and frame_no % 30 == 0:
                            cv2.imwrite(
                                str(save_dir / f"roi_{frame_no:05d}.jpg"), region
                            )
                            box_in_roi = find_die(region)
                            if box_in_roi is not None:
                                dx, dy, dw, dh = box_in_roi
                                cv2.imwrite(
                                    str(save_dir / f"die_{frame_no:05d}.jpg"),
                                    region[dy : dy + dh, dx : dx + dw],
                                )
                took = (time.monotonic() - started) * 1000
                value = stable.update(reading.value if reading else None)

                if value != last_announced:
                    print(
                        "  -- no die in view" if value is None
                        else f"  dice roll: {value}"
                    )
                    last_announced = value

                # ---- draw ----
                shown = frame.copy()
                annotate_projection(
                    shown, projection, None if roi else args.corner
                )
                if box is not None:
                    x1, y1, x2, y2 = box
                    if roi is not None:
                        cv2.rectangle(shown, (x1, y1), (x2, y2), (255, 0, 255), 2)
                    if not args.physical:
                        die_box = find_die(frame[y1:y2, x1:x2])
                        if die_box is not None:
                            dx, dy, dw, dh = die_box
                            cv2.rectangle(
                                shown, (x1 + dx, y1 + dy),
                                (x1 + dx + dw, y1 + dy + dh),
                                (0, 255, 255), 2,
                            )
                    annotate_pips(shown, reading, (x1, y1))

                label = (
                    f"DICE: {value}" if value is not None
                    else (f"reading… ({reading.value})" if reading else "no die")
                )
                cv2.putText(
                    shown, label, (16, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                    (0, 255, 0) if value is not None else (0, 165, 255), 3,
                )
                cv2.putText(
                    shown, f"{took:.0f}ms | frame {frame_no}",
                    (16, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (220, 220, 220), 1,
                )

                if args.save_every and frame_no % args.save_every == 0:
                    cv2.imwrite(
                        str(save_dir / f"frame_{frame_no:05d}.jpg"), shown
                    )
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
