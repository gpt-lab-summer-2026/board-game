"""Read a die face by counting its pips.

Deliberately not a neural net. YOLO can find the phone (COCO has a `cell phone`
class) but it has no notion of a die and cannot read a value off one -- that
would need a custom model trained on labelled dice. Counting pips is a solved
classical-vision problem: pips are round, similarly sized, high-contrast blobs
clustered on one face, and OpenCV's blob detector filters on exactly those
properties. No training data, no new dependencies, and a few milliseconds.

The reader is run on a crop (the phone's screen), not the whole frame, because
a whiteboard full of clutter offers plenty of round dark things to miscount.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

log = logging.getLogger(__name__)

MIN_PIPS = 1
MAX_PIPS = 6


@dataclass
class DiceReading:
    value: int
    """Pip centres in the coordinates of the image passed to read_dice."""
    pips: list[tuple[float, float]] = field(default_factory=list)
    """Which polarity matched: dark pips on a light face, or the reverse."""
    inverted: bool = False
    """Spread of pip areas -- low means they really are the same size."""
    size_spread: float = 0.0


def _blob_detector(
    min_area: float, max_area: float
) -> cv2.SimpleBlobDetector:
    params = cv2.SimpleBlobDetector_Params()
    # Pips are dark on the face; the caller inverts the image to cover the
    # opposite polarity rather than us guessing here.
    params.filterByColor = True
    params.blobColor = 0

    params.filterByArea = True
    params.minArea = min_area
    params.maxArea = max_area

    # A pip is round. These three together are what reject specular glare
    # streaks, text and the phone's own UI chrome.
    params.filterByCircularity = True
    params.minCircularity = 0.7
    params.filterByConvexity = True
    params.minConvexity = 0.8
    params.filterByInertia = True
    params.minInertiaRatio = 0.5

    return cv2.SimpleBlobDetector_create(params)


def _count_pips(
    gray: np.ndarray, inverted: bool
) -> DiceReading | None:
    height, width = gray.shape
    area = height * width
    # A pip occupies a small but not negligible slice of the die face. Tied to
    # the crop size so it scales with how close the phone is held.
    detector = _blob_detector(area * 0.0008, area * 0.05)
    keypoints = detector.detect(gray)

    if not (MIN_PIPS <= len(keypoints) <= MAX_PIPS):
        return None

    sizes = np.array([k.size for k in keypoints], dtype="float64")
    # Real pips on one die are the same size. A mixed bag of blob sizes means
    # we're looking at clutter, not a die face.
    spread = float(sizes.std() / sizes.mean()) if sizes.mean() > 0 else 1.0
    if len(keypoints) > 1 and spread > 0.35:
        return None

    return DiceReading(
        value=len(keypoints),
        pips=[(float(k.pt[0]), float(k.pt[1])) for k in keypoints],
        inverted=inverted,
        size_spread=spread,
    )


def read_dice(image: np.ndarray) -> DiceReading | None:
    """Best pip reading for `image`, or None if it doesn't look like a die.

    Tries dark-pips-on-light and light-pips-on-dark, since a phone dice app may
    be in either theme, and keeps whichever gives the more uniform pip sizes.
    """
    if image.size == 0:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Even out screen backlight before thresholding, and take the edge off
    # camera noise that would otherwise fragment a pip into several blobs.
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    candidates = [
        _count_pips(gray, inverted=False),
        _count_pips(cv2.bitwise_not(gray), inverted=True),
    ]
    found = [c for c in candidates if c is not None]
    if not found:
        return None
    return min(found, key=lambda r: r.size_spread)


class StableReading:
    """Only believes a value once it has held still for a few frames.

    A live feed produces the occasional single-frame misread as the phone moves
    or the exposure shifts; announcing those would make the reader look far
    worse than it is.
    """

    def __init__(self, required: int = 4):
        self.required = required
        self._candidate: int | None = None
        self._streak = 0
        self.value: int | None = None

    def update(self, value: int | None) -> int | None:
        if value != self._candidate:
            self._candidate = value
            self._streak = 0
        self._streak += 1
        if value is not None and self._streak >= self.required:
            self.value = value
        elif value is None and self._streak >= self.required:
            self.value = None
        return self.value


def annotate(
    frame: np.ndarray,
    reading: DiceReading | None,
    origin: tuple[int, int] = (0, 0),
) -> np.ndarray:
    """Draw pip circles onto `frame`; `origin` offsets crop coords to frame coords."""
    if reading is None:
        return frame
    ox, oy = origin
    for x, y in reading.pips:
        cv2.circle(frame, (int(x + ox), int(y + oy)), 10, (0, 0, 255), 2)
    return frame
