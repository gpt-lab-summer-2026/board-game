"""Locate the projected board within a camera frame.

The die is drawn by the game itself, in a corner of the projected image, so the
reader needs to know where the projection sits before it can look at the right
quarter of it. Cropping a fixed quarter of the *camera* frame won't do: the
projection occupies only part of the view and moves whenever the camera or
projector is nudged.

Finding it is classical rather than learned. A projector on a whiteboard is by
far the brightest large rectangle in the room, which a brightness threshold plus
a largest-contour search picks out reliably and in a couple of milliseconds.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Projection:
    """Axis-aligned bounds of the projected area, in frame pixels."""

    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def quadrant(self, corner: str) -> tuple[int, int, int, int]:
        """One quarter of the projection, as (x1, y1, x2, y2) in frame pixels."""
        mid_x = self.x1 + self.width // 2
        mid_y = self.y1 + self.height // 2
        return {
            "top-left": (self.x1, self.y1, mid_x, mid_y),
            "top-right": (mid_x, self.y1, self.x2, mid_y),
            "bottom-left": (self.x1, mid_y, mid_x, self.y2),
            "bottom-right": (mid_x, mid_y, self.x2, self.y2),
        }[corner]


def find_projection(
    frame: np.ndarray,
    min_area_fraction: float = 0.03,
    brightness_percentile: float = 88.0,
) -> Projection | None:
    """Bounds of the projected image, or None if no bright region stands out.

    `brightness_percentile` adapts the threshold to the room instead of using a
    fixed grey level -- a projector in a lit room and one in the dark produce
    very different absolute values, but in both cases the projection is the
    brightest slice of the histogram.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)

    threshold = float(np.percentile(gray, brightness_percentile))
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Close over the dark content *inside* the projection (map, text, UI) so the
    # whole projected area reads as one blob rather than a scatter of fragments.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None

    frame_area = frame.shape[0] * frame.shape[1]
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < frame_area * min_area_fraction:
        log.debug("brightest region too small to be the projection")
        return None

    x, y, w, h = cv2.boundingRect(largest)
    return Projection(x, y, x + w, y + h)


class ProjectionTracker:
    """Smooths the detected projection over recent frames.

    The projection is physically bolted in place, so any frame-to-frame change
    in its bounds is measurement error, not motion -- typically someone leaning
    into the beam or a brightness shift making the threshold clip differently.
    Observed live: the box collapsed from 1607px wide to 1067px for a single
    frame. That matters because piece positions are expressed as fractions of
    the projection, so a bad box makes stationary pieces appear to jump a third
    of the way across the board.

    A per-coordinate median over a short window rejects those outliers while
    still following a genuine, sustained re-aim within a second or so.
    """

    def __init__(
        self,
        window: int = 9,
        max_area_change: float = 0.25,
        reacquire_after: int = 12,
    ):
        self.window = window
        # A hand reaching over the board hides part of the beam and shrinks the
        # detected box. Such a reading must be discarded rather than averaged
        # in, or one reach poisons the median for the whole window -- observed
        # as the box crawling 745 -> 1393px over twelve frames while the
        # projection itself never moved.
        self.max_area_change = max_area_change
        # ...but the box must still be allowed to change for real. Enough
        # consecutive rejections in a row means the projector or camera actually
        # moved, so start over rather than defend a box that no longer exists.
        self.reacquire_after = reacquire_after
        self._history: list[Projection] = []
        self._rejections = 0

    @property
    def current(self) -> Projection | None:
        if not self._history:
            return None
        return Projection(
            int(np.median([p.x1 for p in self._history])),
            int(np.median([p.y1 for p in self._history])),
            int(np.median([p.x2 for p in self._history])),
            int(np.median([p.y2 for p in self._history])),
        )

    def update(self, frame: np.ndarray) -> Projection | None:
        found = find_projection(frame)
        settled = self.current

        if found is not None and settled is not None:
            found_area = found.width * found.height
            settled_area = settled.width * settled.height
            if settled_area > 0:
                change = abs(found_area - settled_area) / settled_area
                if change > self.max_area_change:
                    self._rejections += 1
                    if self._rejections < self.reacquire_after:
                        return settled  # transient occlusion; hold the last box
                    log.info(
                        "projection changed for %d frames; re-acquiring",
                        self._rejections,
                    )
                    self._history.clear()
                    self._rejections = 0

        if found is not None:
            self._rejections = 0
            self._history.append(found)
            if len(self._history) > self.window:
                self._history.pop(0)
        return self.current

    def reset(self) -> None:
        self._history.clear()
        self._rejections = 0


def annotate(
    frame: np.ndarray,
    projection: Projection | None,
    corner: str | None = None,
) -> np.ndarray:
    """Outline the projection, and the working quadrant if one is named."""
    if projection is None:
        return frame
    cv2.rectangle(
        frame,
        (projection.x1, projection.y1),
        (projection.x2, projection.y2),
        (0, 200, 255),
        2,
    )
    cv2.putText(
        frame, "projection", (projection.x1, max(projection.y1 - 8, 12)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2,
    )
    if corner is not None:
        qx1, qy1, qx2, qy2 = projection.quadrant(corner)
        cv2.rectangle(frame, (qx1, qy1), (qx2, qy2), (255, 0, 255), 2)
        cv2.putText(
            frame, corner, (qx1 + 4, qy1 + 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2,
        )
    return frame
