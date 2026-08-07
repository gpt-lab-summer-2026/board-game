"""ArUco marker detection.

Fiducial markers, not a neural net, are the right tool for tracking pieces on a
projector-lit board: cv2.aruco gives you each marker's id, its four corners and
therefore its position and orientation, runs in milliseconds on this CPU, and
is unbothered by the projector washing out colour and contrast. A general
object detector (YOLO and friends) cannot recognise an ArUco marker at all
without first being trained on a labelled dataset of your specific markers --
it would be strictly more work for a strictly worse result.

Markers come from a *dictionary*, and a marker only decodes under the
dictionary it was generated from. Since a printed sheet rarely says which one
it used, `identify_dictionary` sweeps the common ones and reports what matched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)

# What the printed board markers actually use -- identified by sweeping all 27
# of OpenCV's dictionaries against a photo of the physical sheet, which returned
# a clean sequential 0/1/2/3 under this one and incoherent ids (duplicates,
# 1023) under everything else.
DEFAULT_DICTIONARY = "DICT_APRILTAG_36H10"

# Swept by identify_dictionary when the markers are unknown. 36H10 leads because
# it's what we have; the 4x4/5x5/6x6 families follow because they're what online
# generators hand out by default.
COMMON_DICTIONARIES: tuple[str, ...] = (
    "DICT_APRILTAG_36H10",
    "DICT_APRILTAG_36H11",
    "DICT_APRILTAG_25H9",
    "DICT_4X4_50",
    "DICT_4X4_100",
    "DICT_4X4_250",
    "DICT_5X5_50",
    "DICT_5X5_100",
    "DICT_5X5_250",
    "DICT_6X6_50",
    "DICT_6X6_100",
    "DICT_6X6_250",
    "DICT_7X7_50",
    "DICT_ARUCO_ORIGINAL",
    "DICT_ARUCO_MIP_36H12",
)


@dataclass
class Marker:
    id: int
    """Corners in image pixels, clockwise from top-left of the marker."""
    corners: np.ndarray

    @property
    def center(self) -> tuple[float, float]:
        return (
            float(self.corners[:, 0].mean()),
            float(self.corners[:, 1].mean()),
        )

    @property
    def side_px(self) -> float:
        """Mean edge length -- a rough proxy for how close/large the marker is."""
        pts = self.corners
        return float(
            np.mean(
                [np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]
            )
        )


def _detector(dictionary_name: str) -> cv2.aruco.ArucoDetector:
    dictionary = cv2.aruco.getPredefinedDictionary(
        getattr(cv2.aruco, dictionary_name)
    )
    params = cv2.aruco.DetectorParameters()
    # Corner refinement costs a little time and buys sub-pixel corners, which is
    # what makes a position stable enough to map onto a board square.
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    # The default window sweep (3..23 step 10) is too narrow for a surface lit
    # unevenly -- on the first real photo it binarised only 1 of 4 markers, the
    # other three being washed out by ceiling-light glare. Widening the sweep
    # found all 4. Costs a few ms; worth it under a projector, which makes
    # uneven lighting the normal case rather than the exception.
    params.adaptiveThreshWinSizeMax = 53
    params.adaptiveThreshWinSizeStep = 6
    return cv2.aruco.ArucoDetector(dictionary, params)


def detect(
    frame: np.ndarray, dictionary_name: str = DEFAULT_DICTIONARY
) -> list[Marker]:
    """Markers found in `frame` under one dictionary."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _rejected = _detector(dictionary_name).detectMarkers(gray)
    if ids is None:
        return []
    return [
        Marker(id=int(marker_id), corners=corner_set.reshape(4, 2))
        for marker_id, corner_set in zip(ids.flatten(), corners)
    ]


def identify_dictionary(
    frame: np.ndarray, candidates: tuple[str, ...] = COMMON_DICTIONARIES
) -> list[tuple[str, list[Marker]]]:
    """Try every candidate dictionary; return those that found anything, best first.

    A marker can decode under more than one dictionary (the families overlap),
    so this reports all hits rather than guessing -- the one with the most
    markers is usually the one the sheet was printed from.
    """
    hits = []
    for name in candidates:
        found = detect(frame, name)
        if found:
            hits.append((name, found))
    hits.sort(key=lambda pair: len(pair[1]), reverse=True)
    return hits


def annotate(frame: np.ndarray, markers: list[Marker]) -> np.ndarray:
    """Copy of `frame` with each marker outlined and labelled, for eyeballing."""
    out = frame.copy()
    for marker in markers:
        pts = marker.corners.astype(int).reshape(-1, 1, 2)
        cv2.polylines(out, [pts], True, (0, 255, 0), 2)
        cx, cy = marker.center
        cv2.putText(
            out, str(marker.id), (int(cx) - 10, int(cy) + 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
        )
    return out
