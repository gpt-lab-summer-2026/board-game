"""General object detection, for the things ArUco can't see.

Markers are handled by vision/aruco.py and should stay there -- it's faster and
exact. This module is for unmarked things: a hand reaching over the board, dice,
an unlabelled piece.

Uses ultralytics YOLO rather than the darknet checkout in /darknet, for a
practical reason: OpenCV 5 removed the Darknet importer (`readNetFromDarknet` is
gone, only ONNX/TFLite/TensorFlow remain), so .cfg/.weights can no longer be
loaded in-process -- driving them means shelling out to the darknet binary once
per frame. Measured on this Pi, that binary needs 1.06s/frame for yolov4-tiny
and 22.3s/frame for full yolov4. The darknet build still works standalone if you
want it; it just isn't what a live camera loop should be calling.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

# Keep ultralytics from phoning home or writing a settings file into $HOME.
os.environ.setdefault("YOLO_OFFLINE", "1")
os.environ.setdefault("YOLO_VERBOSE", "0")

DEFAULT_MODEL = "models/yolov8n.pt"


@dataclass
class Detection:
    label: str
    confidence: float
    """(x1, y1, x2, y2) in image pixels."""
    box: tuple[float, float, float, float]

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2, (y1 + y2) / 2)


class ObjectDetector:
    def __init__(
        self,
        model_path: str = DEFAULT_MODEL,
        confidence: float = 0.35,
        image_size: int = 416,
    ):
        from ultralytics import YOLO  # lazy: pulls in torch

        self.confidence = confidence
        # 416 rather than the 640 default: on this CPU the cost scales with area,
        # and the board fills the frame, so the extra resolution buys little.
        self.image_size = image_size
        log.info("Loading %s...", model_path)
        self._model = YOLO(model_path)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self._model.predict(
            frame,
            imgsz=self.image_size,
            conf=self.confidence,
            verbose=False,
        )
        out: list[Detection] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                out.append(
                    Detection(
                        label=names[int(box.cls[0])],
                        confidence=float(box.conf[0]),
                        box=(x1, y1, x2, y2),
                    )
                )
        return out


def annotate(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """Copy of `frame` with each detection boxed and labelled."""
    import cv2

    out = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det.box)
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 128, 0), 2)
        cv2.putText(
            out,
            f"{det.label} {det.confidence:.0%}",
            (x1, max(y1 - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 128, 0),
            2,
        )
    return out
