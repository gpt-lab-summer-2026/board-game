"""Generating tileable wall and floor textures.

Drawn procedurally rather than fetched, for two reasons: nothing here needs a
licence check before it goes in someone's campaign, and a seamless tile is
easier to guarantee when you control the wrap than when you crop a photo.

Every texture is generated to tile: anything drawn near an edge is drawn again
on the opposite edge, so a wall built from many one-cell rects has no visible
seams between them.
"""
from __future__ import annotations

import random
import zlib
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

# One grid cell at PlanarAlly's default zoom. Small enough to stay cheap on a
# Pi when a wall is fifty of them.
TILE = 100


def _noise(size: int, rng: random.Random, amount: int) -> Image.Image:
    """Fine grain, so flat fills don't look like plastic."""
    img = Image.new("L", (size, size))
    img.putdata([rng.randint(128 - amount, 128 + amount) for _ in range(size * size)])
    return img.filter(ImageFilter.GaussianBlur(0.6))


def _apply_grain(base: Image.Image, rng: random.Random, amount: int = 14) -> Image.Image:
    grain = _noise(base.width, rng, amount).convert("RGB")
    return Image.blend(base, grain, 0.18)


def brick(rng: random.Random, colour=(150, 74, 60), mortar=(198, 192, 182)) -> Image.Image:
    img = Image.new("RGB", (TILE, TILE), mortar)
    d = ImageDraw.Draw(img)
    rows, gap = 4, 3
    h = TILE // rows
    for row in range(rows):
        # Alternate rows are offset by half a brick, and the offset wraps, so
        # the tile still lines up with itself horizontally.
        offset = 0 if row % 2 == 0 else -TILE // 4
        for col in range(-1, 3):
            x0 = col * (TILE // 2) + offset
            shade = tuple(max(0, min(255, c + rng.randint(-18, 18))) for c in colour)
            d.rectangle(
                [x0 + gap, row * h + gap, x0 + TILE // 2 - gap, (row + 1) * h - gap],
                fill=shade,
            )
    return _apply_grain(img, rng)


def stone(rng: random.Random, colour=(122, 122, 118)) -> Image.Image:
    img = Image.new("RGB", (TILE, TILE), colour)
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        r = rng.randint(8, 26)
        shade = tuple(max(0, min(255, c + rng.randint(-26, 22))) for c in colour)
        # Draw every blob four times, wrapped, so edges match across tiles.
        for dx in (-TILE, 0, TILE):
            for dy in (-TILE, 0, TILE):
                d.ellipse([x + dx - r, y + dy - r, x + dx + r, y + dy + r], fill=shade)
    return _apply_grain(img.filter(ImageFilter.GaussianBlur(0.8)), rng)


def wood(rng: random.Random, colour=(126, 88, 52)) -> Image.Image:
    img = Image.new("RGB", (TILE, TILE), colour)
    d = ImageDraw.Draw(img)
    for x in range(0, TILE, 4):
        shade = tuple(max(0, min(255, c + rng.randint(-20, 16))) for c in colour)
        d.line([(x, 0), (x, TILE)], fill=shade, width=4)
    for _ in range(3):
        y = rng.randrange(TILE)
        d.line([(0, y), (TILE, y)], fill=(70, 48, 28), width=2)
    return _apply_grain(img, rng, 10)


def dirt(rng: random.Random, colour=(104, 86, 62)) -> Image.Image:
    img = Image.new("RGB", (TILE, TILE), colour)
    d = ImageDraw.Draw(img)
    for _ in range(240):
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        r = rng.randint(1, 3)
        shade = tuple(max(0, min(255, c + rng.randint(-30, 26))) for c in colour)
        d.ellipse([x - r, y - r, x + r, y + r], fill=shade)
    return _apply_grain(img, rng, 18)


def metal(rng: random.Random, colour=(108, 112, 120)) -> Image.Image:
    img = Image.new("RGB", (TILE, TILE), colour)
    d = ImageDraw.Draw(img)
    for y in range(0, TILE, 2):
        shade = tuple(max(0, min(255, c + rng.randint(-10, 10))) for c in colour)
        d.line([(0, y), (TILE, y)], fill=shade)
    # Rivets, wrapped like the stone blobs.
    for pos in ((12, 12), (TILE - 12, 12), (12, TILE - 12), (TILE - 12, TILE - 12)):
        d.ellipse([pos[0] - 4, pos[1] - 4, pos[0] + 4, pos[1] + 4], fill=(78, 82, 90))
    return _apply_grain(img, rng, 8)


def lava(rng: random.Random) -> Image.Image:
    img = Image.new("RGB", (TILE, TILE), (48, 18, 12))
    d = ImageDraw.Draw(img)
    for _ in range(30):
        x, y = rng.randrange(TILE), rng.randrange(TILE)
        r = rng.randint(6, 20)
        heat = (rng.randint(200, 255), rng.randint(70, 140), 20)
        for dx in (-TILE, 0, TILE):
            for dy in (-TILE, 0, TILE):
                d.ellipse([x + dx - r, y + dy - r, x + dx + r, y + dy + r], fill=heat)
    return img.filter(ImageFilter.GaussianBlur(2.5))


GENERATORS = {
    "brick": brick,
    "stone": stone,
    "wood": wood,
    "dirt": dirt,
    "metal": metal,
    "lava": lava,
}


def make(name: str, seed: int = 0) -> bytes:
    """One texture as PNG bytes, deterministic for a given name and seed.

    Seeded with crc32, not `str.__hash__`: Python randomises string hashing
    per process unless PYTHONHASHSEED is fixed, so the original version
    produced a different image on every run while claiming otherwise.
    Re-uploading a texture would have silently changed every wall using it.
    """
    generator = GENERATORS[name]
    return encode(generator(random.Random(zlib.crc32(f"{name}-{seed}".encode()))))


def encode(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
