"""Point the camera at your printed markers and see what it finds.

    python -m vision.test_camera                 # sweep every common dictionary
    python -m vision.test_camera --dict DICT_4X4_50 --watch
    python -m vision.test_camera --width 2592 --height 1944   # small/far markers

Writes an annotated JPEG so you can check framing and focus without needing a
window, which matters over SSH.
"""
from __future__ import annotations

import argparse
import logging
import time

from .aruco import COMMON_DICTIONARIES, annotate, detect, identify_dictionary
from .camera import Camera, CameraConfig


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--device", type=int, default=0, help="/dev/videoN index")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument(
        "--dict",
        dest="dictionary",
        default=None,
        help="use one dictionary instead of sweeping all of them",
    )
    p.add_argument(
        "--watch",
        action="store_true",
        help="keep detecting until Ctrl+C (needs --dict)",
    )
    p.add_argument(
        "--objects",
        action="store_true",
        help="also run general object detection (people, dice, hands) -- see vision/objects.py",
    )
    p.add_argument(
        "--out",
        default="/tmp/aruco_test.jpg",
        help="where to write the annotated frame",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def describe(markers) -> str:
    if not markers:
        return "none"
    return ", ".join(
        f"id={m.id} at ({m.center[0]:.0f},{m.center[1]:.0f}) {m.side_px:.0f}px"
        for m in sorted(markers, key=lambda m: m.id)
    )


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = CameraConfig(
        device=args.device, width=args.width, height=args.height
    )
    with Camera(cfg) as cam:
        if args.watch:
            if not args.dictionary:
                raise SystemExit("--watch needs --dict (sweeping every frame is too slow)")
            print(f"Watching for {args.dictionary} markers. Ctrl+C to stop.")
            try:
                while True:
                    started = time.monotonic()
                    markers = detect(cam.read(), args.dictionary)
                    took = (time.monotonic() - started) * 1000
                    print(f"[{took:5.0f}ms] {len(markers):2d} marker(s): {describe(markers)}")
                    time.sleep(0.2)
            except KeyboardInterrupt:
                print("\nstopped.")
            return

        frame = cam.read()
        print(f"captured {frame.shape[1]}x{frame.shape[0]}")

        if args.dictionary:
            markers = detect(frame, args.dictionary)
            print(f"{args.dictionary}: {len(markers)} marker(s): {describe(markers)}")
            best = markers
        else:
            started = time.monotonic()
            hits = identify_dictionary(frame)
            took = time.monotonic() - started
            if not hits:
                print(
                    f"\nNo markers found in any of {len(COMMON_DICTIONARIES)} dictionaries "
                    f"({took:.1f}s).\n"
                    "Check: is the sheet in frame and in focus, evenly lit, and not too "
                    "small? Re-run with --width 2592 --height 1944 for distant markers, "
                    f"and open {args.out} to see what the camera actually saw."
                )
            else:
                print(f"\nMatched {len(hits)} dictionary/-ies in {took:.1f}s:")
                for name, markers in hits:
                    print(f"  {name:24} {len(markers):2d} marker(s): {describe(markers)}")
                print(
                    f"\nMost likely: {hits[0][0]} -- pass it as --dict to skip the sweep."
                )
            best = hits[0][1] if hits else []

        import cv2

        annotated = annotate(frame, best)

        if args.objects:
            from .objects import ObjectDetector
            from .objects import annotate as annotate_objects

            started = time.monotonic()
            detections = ObjectDetector().detect(frame)
            took = (time.monotonic() - started) * 1000
            print(f"\nobjects ({took:.0f}ms): {len(detections)} found")
            for d in sorted(detections, key=lambda d: -d.confidence):
                print(f"  {d.label:14} {d.confidence:.0%} at ({d.center[0]:.0f},{d.center[1]:.0f})")
            annotated = annotate_objects(annotated, detections)

        cv2.imwrite(args.out, annotated)
        print(f"annotated frame -> {args.out}")


if __name__ == "__main__":
    main()
