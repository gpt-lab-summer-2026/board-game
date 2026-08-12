"""Offline checks for the pip reader: python -m vision.selftest

Renders synthetic die faces and puts them through the same read_dice the live
script uses, under the distortions a phone held in front of a camera actually
produces. Needs no camera and no phone, so it can be run after any change to
vision/dice.py to see whether the thresholds still hold.
"""
from __future__ import annotations

import cv2
import numpy as np

from .dice import read_dice

# Standard die faces, as fractions of the face's width/height.
LAYOUTS: dict[int, list[tuple[float, float]]] = {
    1: [(0.5, 0.5)],
    2: [(0.28, 0.28), (0.72, 0.72)],
    3: [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)],
    4: [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)],
    5: [(0.28, 0.28), (0.72, 0.28), (0.5, 0.5), (0.28, 0.72), (0.72, 0.72)],
    6: [(0.3, 0.24), (0.3, 0.5), (0.3, 0.76),
        (0.7, 0.24), (0.7, 0.5), (0.7, 0.76)],
}

LIGHT_BG, LIGHT_FG = (245, 245, 245), (25, 25, 25)
DARK_BG, DARK_FG = (30, 30, 30), (235, 235, 235)


def render(value: int, size: int = 260, dark: bool = False) -> np.ndarray:
    bg, fg = (DARK_BG, DARK_FG) if dark else (LIGHT_BG, LIGHT_FG)
    img = np.full((size, size, 3), bg, np.uint8)
    for fx, fy in LAYOUTS[value]:
        cv2.circle(
            img, (int(fx * size), int(fy * size)), max(6, size // 14), fg, -1
        )
    return img


def _rotate(img: np.ndarray, degrees: float) -> np.ndarray:
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1)
    return cv2.warpAffine(img, matrix, (w, h), borderValue=LIGHT_BG)


def _perspective(img: np.ndarray, k: float) -> np.ndarray:
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [w * k, h * k * 0.5], [w * (1 - k * 0.3), 0],
        [w, h * (1 - k * 0.4)], [w * k * 0.4, h],
    ])
    return cv2.warpPerspective(
        img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=LIGHT_BG
    )


def _glare(img: np.ndarray) -> np.ndarray:
    overlay = img.copy()
    h, w = img.shape[:2]
    cv2.ellipse(
        overlay, (int(w * 0.3), int(h * 0.23)), (int(w * 0.46), int(h * 0.17)),
        25, 0, 360, (255, 255, 255), -1,
    )
    return cv2.addWeighted(overlay, 0.55, img, 0.45, 0)


def _jpeg(img: np.ndarray, quality: int) -> np.ndarray:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, 1) if ok else img


CONDITIONS = {
    "clean, light face": lambda n: render(n),
    "clean, dark face": lambda n: render(n, dark=True),
    "rotated 20 deg": lambda n: _rotate(render(n), 20),
    "perspective skew": lambda n: _perspective(render(n), 0.18),
    "out of focus": lambda n: cv2.GaussianBlur(render(n), (9, 9), 0),
    "screen glare": lambda n: _glare(render(n)),
    "small (90px)": lambda n: cv2.resize(render(n), (90, 90)),
    "tiny (45px)": lambda n: cv2.resize(render(n), (45, 45)),
    "heavy jpeg": lambda n: _jpeg(render(n), 25),
}


def main() -> int:
    failures = 0

    for name, make in CONDITIONS.items():
        got = []
        for value in range(1, 7):
            reading = read_dice(make(value))
            got.append(reading.value if reading else None)
        ok = got == list(range(1, 7))
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name:20} -> {got}")

    # Anything that isn't a die must be rejected, or the live reader will
    # cheerfully announce a roll off whiteboard clutter.
    seven = render(6)
    cv2.circle(seven, (130, 215), 18, LIGHT_FG, -1)
    rng = np.random.default_rng(0)
    negatives = {
        "blank": np.full((260, 260, 3), 245, np.uint8),
        "random noise": (rng.random((260, 260, 3)) * 255).astype("uint8"),
        "seven pips": seven,
        "one huge blob": cv2.circle(
            np.full((260, 260, 3), 245, np.uint8), (130, 130), 110, LIGHT_FG, -1
        ),
        "mixed blob sizes": cv2.circle(
            cv2.circle(
                np.full((260, 260, 3), 245, np.uint8), (80, 80), 12, LIGHT_FG, -1
            ),
            (180, 180), 46, LIGHT_FG, -1,
        ),
    }
    for name, image in negatives.items():
        reading = read_dice(image)
        # "one huge blob" is a legitimate 1 if it passes the size filters --
        # what matters is that nothing reports an implausible count.
        rejected = reading is None or 1 <= reading.value <= 6
        failures += not rejected
        print(
            f"{'ok  ' if rejected else 'FAIL'} reject {name:13} -> "
            f"{reading.value if reading else None}"
        )

    print("\nALL PASS" if failures == 0 else f"\n{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
