"""USB camera capture.

The board camera is a UVC device (Sunplus UHD 4K) on /dev/video0. It offers
MJPG at everything from 640x480 up to 3840x2160; MJPG matters because the
uncompressed YUYV alternative won't fit in USB bandwidth at the larger sizes.

Deliberately plain OpenCV rather than PipeWire: unlike the microphone (see
voice/audio.py, which had to abandon PortAudio entirely), V4L2 video capture on
this Pi has given no trouble.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    device: int = 0
    # Measured against the printed markers at whiteboard distance (~110px per
    # marker edge at full sensor res): 720p detects 4/4 on every frame at ~100ms,
    # 2592x1944 also 4/4 but ~196ms. So 720p is the default and the higher mode
    # is there for markers that are smaller or further away than these.
    width: int = 1280
    height: int = 720
    # Frames the driver buffers before we read. Set to 1 so a grab returns what
    # the camera sees *now* rather than a stale queued frame -- important when
    # detection takes longer than a frame interval.
    buffer_frames: int = 1
    warmup_frames: int = 5  # early frames come back black while gain settles


class Camera:
    def __init__(self, cfg: CameraConfig | None = None):
        self.cfg = cfg or CameraConfig()
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        cap = cv2.VideoCapture(self.cfg.device, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(
                f"could not open /dev/video{self.cfg.device}. Is the camera plugged in? "
                f"`v4l2-ctl --list-devices` shows what's attached."
            )
        # MJPG must be set before the frame size, or the driver picks YUYV and
        # silently caps the resolution to whatever fits the USB bus.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.cfg.buffer_frames)
        self._cap = cap

        actual = (
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        if actual != (self.cfg.width, self.cfg.height):
            log.warning(
                "camera gave %dx%d instead of the requested %dx%d",
                *actual, self.cfg.width, self.cfg.height,
            )
        for _ in range(self.cfg.warmup_frames):
            cap.read()
        log.info("camera open at %dx%d", *actual)

    def read(self) -> np.ndarray:
        if self._cap is None:
            raise RuntimeError("call open() first")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("camera read failed (device unplugged?)")
        return frame

    def reopen(self) -> None:
        """Drop the handle and acquire the device again.

        This camera re-enumerates in practice -- it has moved between USB ports
        mid-session, which invalidates the open handle and makes every
        subsequent read fail. A long-running loop should try this before giving
        up rather than dying on a transient.
        """
        self.close()
        self.open()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
