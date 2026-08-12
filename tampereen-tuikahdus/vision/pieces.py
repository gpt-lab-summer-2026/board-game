"""Locate the playing pieces on the projected board.

Right now the pieces are dark blue magnets. They are found by colour and
darkness rather than by an object detector: COCO has no `magnet` class, and
training one would mean building a labelled dataset of these specific tokens.
Against a projection whose median brightness is saturated white, an opaque disc
that reflects almost nothing is about as unambiguous a signal as vision offers
-- measured V ~100 against a projection median of 255.

This is a stopgap. Once AprilTags are stuck on top of the magnets, switch to
vision/aruco.py: a tag carries an *identity*, so pieces stop being
interchangeable blobs and become "player 2", and it yields orientation for free.
Positions here are therefore reported as fractions of the projection, the same
frame of reference a tag-based tracker would use, so the swap doesn't ripple.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from .projection import Projection

log = logging.getLogger(__name__)


@dataclass
class PieceAppearance:
    """What a piece looks like against the projection, in OpenCV HSV."""

    # Measured on the real magnets: H 89-97, S 97-167, V 97-111, against a
    # projection whose median V is 255. Loose enough to survive the projector
    # tinting them and the camera's white balance wandering.
    hue_min: int = 75
    hue_max: int = 135
    min_saturation: int = 60
    max_value: int = 150
    # As a fraction of the projection's width. The magnets measure ~1.4%; the
    # ceiling is what rejects real-world clutter that overlaps the projection's
    # bounding box, such as the dark equipment at its right edge (8.7%).
    min_diameter_fraction: float = 0.004
    max_diameter_fraction: float = 0.045
    # A disc seen at an angle is still roughly round and still fills its box.
    min_aspect: float = 0.6
    max_aspect: float = 1.6
    min_fill: float = 0.55
    # The projection's bounding box overshoots slightly onto the whiteboard and
    # its pen ledge, which is where a blue marker got picked up as a third
    # piece (v=0.978). Nothing the game draws lives in the outermost slice, so
    # ignoring it is free.
    edge_margin: float = 0.03


@dataclass
class Piece:
    """Where a piece is. `u`/`v` are fractions of the projection, so they stay
    meaningful across camera resolutions and reframings."""

    x: int
    y: int
    u: float
    v: float
    diameter: int

    def moved_from(self, other: "Piece", tolerance: float = 0.01) -> bool:
        return abs(self.u - other.u) > tolerance or abs(self.v - other.v) > tolerance


def find_pieces(
    frame: np.ndarray,
    projection: Projection,
    look: PieceAppearance | None = None,
    limit: int | None = None,
) -> list[Piece]:
    """Pieces on the board, largest first. Coordinates are in frame pixels."""
    look = look or PieceAppearance()
    roi = frame[projection.y1 : projection.y2, projection.x1 : projection.x2]
    if roi.size == 0:
        return []

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = (
        (hsv[:, :, 2] < look.max_value)
        & (hsv[:, :, 1] > look.min_saturation)
        & (hsv[:, :, 0] > look.hue_min)
        & (hsv[:, :, 0] < look.hue_max)
    ).astype("uint8") * 255
    # Open first to drop speckle, then close so a magnet with a glare highlight
    # across it still reads as one blob.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))

    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    min_d = projection.width * look.min_diameter_fraction
    max_d = projection.width * look.max_diameter_fraction

    found: list[Piece] = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if h == 0 or w == 0:
            continue
        diameter = (w + h) / 2
        if not (min_d <= diameter <= max_d):
            continue
        if not (look.min_aspect < w / h < look.max_aspect):
            continue
        if area / (w * h) < look.min_fill:
            continue
        cx, cy = centroids[i]
        u, v = cx / projection.width, cy / projection.height
        margin = look.edge_margin
        if not (margin < u < 1 - margin and margin < v < 1 - margin):
            continue
        found.append(
            Piece(
                x=int(cx) + projection.x1,
                y=int(cy) + projection.y1,
                u=float(u),
                v=float(v),
                diameter=int(diameter),
            )
        )

    found.sort(key=lambda p: p.diameter, reverse=True)
    return found[:limit] if limit else found


def annotate(frame: np.ndarray, pieces: list[Piece]) -> np.ndarray:
    """Ring and number each piece, in the order find_pieces returned them."""
    for index, piece in enumerate(pieces, start=1):
        radius = max(piece.diameter, 12)
        cv2.circle(frame, (piece.x, piece.y), radius, (0, 0, 255), 3)
        cv2.putText(
            frame, str(index), (piece.x + radius + 4, piece.y + 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2,
        )
    return frame
