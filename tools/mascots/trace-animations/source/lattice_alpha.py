"""Lattice fit on alpha edges only (clean silhouette staircases)."""
from __future__ import annotations

import cmath
import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"


def profiles(im: Image.Image):
    px = im.load()
    w, h = im.size
    ex = [0.0] * w
    for x in range(1, w):
        s = 0.0
        for y in range(0, h):
            s += abs(px[x, y][3] - px[x - 1, y][3])
        ex[x] = s
    ey = [0.0] * h
    for y in range(1, h):
        s = 0.0
        for x in range(0, w):
            s += abs(px[x, y][3] - px[x, y - 1][3])
        ey[y] = s
    return ex, ey


def fit(e, label):
    n = len(e)
    out = []
    s = 9.0
    while s <= 11.5:
        re = im_ = wsum = 0.0
        for x, wgt in enumerate(e):
            if wgt <= 0:
                continue
            ang = 2 * math.pi * x / s
            re += wgt * math.cos(ang)
            im_ += wgt * math.sin(ang)
            wsum += wgt
        mag = (re * re + im_ * im_) ** 0.5 / max(1.0, wsum)
        phi = (-cmath.phase(complex(re, im_)) * s / (2 * math.pi)) % s
        out.append((mag, s, phi))
        s += 0.01
    out.sort(reverse=True)
    print(f"{label}:")
    for mag, s, phi in out[:6]:
        print(f"   {mag:.4f}  block {s:.3f}px  phase {phi:.2f}  cells/1254 = {1254/s:.2f}")


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    ex, ey = profiles(im)
    fit(ex, "x (alpha edges)")
    fit(ey, "y (alpha edges)")


if __name__ == "__main__":
    main()
