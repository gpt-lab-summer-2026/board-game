"""Track the playing pieces on the projected board, and report when they move.

    python -m vision.test_pieces                 # window + saved frames
    python -m vision.test_pieces --no-window     # headless
    python -m vision.test_pieces --expect 2      # warn unless exactly 2 are seen

Prints a line only when the board changes -- a piece appears, vanishes, or is
picked up and put down somewhere else -- so leaving it running and moving a
magnet gives you one line per move rather than a scrolling wall of coordinates.

Positions are given both in frame pixels and as fractions of the projection.
The fractions are the useful ones: they survive the camera being re-aimed or the
resolution being changed, and they are what a later AprilTag tracker will report
too (see vision/pieces.py on why tags supersede this).

Keys in the window: q or Esc quits, s saves the current frame.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2

from .camera import Camera, CameraConfig
from .pieces import Piece, annotate as annotate_pieces, find_pieces
from .projection import ProjectionTracker, annotate as annotate_projection

log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--device", type=int, default=0)
    # The magnets are ~22px across at this resolution; at 720p they'd be ~11px,
    # which is too few to judge roundness on.
    p.add_argument("--width", type=int, default=2592)
    p.add_argument("--height", type=int, default=1944)
    p.add_argument(
        "--expect", type=int, default=None,
        help="how many pieces should be on the board; warns when the count differs",
    )
    p.add_argument(
        "--tolerance", type=float, default=0.01,
        help="how far a piece must move (as a fraction of the projection) to "
        "count as having moved, rather than jitter",
    )
    p.add_argument(
        "--settle-frames", type=int, default=3,
        help="frames a new arrangement must persist before it's reported -- "
        "stops a hand passing over the board generating spurious moves",
    )
    p.add_argument("--no-window", action="store_true")
    p.add_argument("--save-dir", default="/tmp/piece_frames")
    p.add_argument(
        "--save-every", type=int, default=0,
        help="save every Nth frame (0 = only save when the board changes)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def describe(pieces: list[Piece]) -> str:
    if not pieces:
        return "none"
    return "  ".join(
        f"#{i}: ({p.x},{p.y})px u={p.u:.3f} v={p.v:.3f}"
        for i, p in enumerate(pieces, start=1)
    )


def arrangement_changed(
    now: list[Piece], before: list[Piece], tolerance: float
) -> bool:
    if len(now) != len(before):
        return True
    # Pieces are interchangeable blobs until AprilTags give them identities, so
    # compare as a set: match each new piece to the nearest previous one.
    remaining = list(before)
    for piece in now:
        nearest = min(
            remaining,
            key=lambda q: (q.u - piece.u) ** 2 + (q.v - piece.v) ** 2,
            default=None,
        )
        if nearest is None or piece.moved_from(nearest, tolerance):
            return True
        remaining.remove(nearest)
    return False


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    save_dir = Path(args.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    tracker = ProjectionTracker()
    reported: list[Piece] = []
    pending: list[Piece] | None = None
    pending_streak = 0
    frame_no = 0
    saved = 0
    read_failures = 0
    first_report = True

    print(
        "Tracking pieces. Move a magnet and it will print the new arrangement. "
        + ("q/Esc quit, s save. " if not args.no_window else "")
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
                    except Exception:  # noqa: BLE001 - retry next pass
                        log.debug("reopen failed", exc_info=True)
                    continue
                frame_no += 1
                height = frame.shape[0]

                started = time.monotonic()
                # Smoothed, not raw: the projection is bolted in place, so a
                # frame where its detected bounds collapse is measurement error
                # -- and since piece positions are fractions of those bounds, a
                # bad box makes stationary pieces look like they teleported.
                projection = tracker.update(frame)
                pieces = (
                    find_pieces(frame, projection) if projection else []
                )
                took = (time.monotonic() - started) * 1000

                # Require the new arrangement to hold still, so a hand reaching
                # across doesn't count as everyone moving at once.
                if pending is None or arrangement_changed(
                    pieces, pending, args.tolerance
                ):
                    pending = pieces
                    pending_streak = 1
                else:
                    pending_streak += 1

                # >= rather than ==: with an exact match the report could only
                # ever fire on the one frame the streak hit the threshold, so a
                # single noisy comparison on that frame lost the update until
                # something moved again.
                if pending_streak >= args.settle_frames and arrangement_changed(
                    pieces, reported, args.tolerance
                ):
                    reported = pieces
                    prefix = "found" if first_report else "moved"
                    first_report = False
                    print(f"  {prefix} {len(pieces)} piece(s): {describe(pieces)}")
                    if args.expect is not None and len(pieces) != args.expect:
                        print(
                            f"    ! expected {args.expect}; "
                            "check lighting, or a piece may be off the board"
                        )
                    out = save_dir / f"change_{frame_no:05d}.jpg"
                    shown = annotate_pieces(
                        annotate_projection(frame.copy(), projection), pieces
                    )
                    cv2.imwrite(str(out), shown)
                    saved += 1

                # ---- draw ----
                shown = annotate_pieces(
                    annotate_projection(frame.copy(), projection), pieces
                )
                cv2.putText(
                    shown,
                    f"{len(pieces)} piece(s)"
                    + ("" if projection else "  [no projection]"),
                    (16, 56), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                    (0, 255, 0) if pieces else (0, 165, 255), 3,
                )
                cv2.putText(
                    shown, f"{took:.0f}ms | frame {frame_no}",
                    (16, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (220, 220, 220), 2,
                )

                if args.save_every and frame_no % args.save_every == 0:
                    cv2.imwrite(
                        str(save_dir / f"frame_{frame_no:05d}.jpg"), shown
                    )
                    saved += 1

                if not args.no_window:
                    cv2.imshow("pieces", shown)
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

    print(f"\nstopped after {frame_no} frames; {saved} images in {save_dir}")


if __name__ == "__main__":
    main()
