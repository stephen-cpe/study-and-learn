"""Fourier fit of the pixel lattice (block size + phase) on each axis.

Edge positions of a pixel-art upscale lie on x = phi + s*k.  Summing edge
energy as a complex phasor e^(2*pi*i*x/s) over candidate spacings s peaks at
the true block size, and its phase gives the lattice offset.
"""
from __future__ import annotations

import cmath
import math
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"


def edge_profile(im: Image.Image, axis: str) -> list[float]:
    sm = im.filter(ImageFilter.GaussianBlur(1.0))
    px = sm.load()
    w, h = im.size
    n = w if axis == "x" else h
    e = [0.0] * n
    if axis == "x":
        for x in range(1, w):
            s = 0.0
            for y in range(0, h, 2):
                a, b = px[x, y], px[x - 1, y]
                s += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) + abs(a[3] - b[3]) // 4
            e[x] = s
    else:
        for y in range(1, h):
            s = 0.0
            for x in range(0, w, 2):
                a, b = px[x, y], px[x, y - 1]
                s += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) + abs(a[3] - b[3]) // 4
            e[y] = s
    return e


def fit(e: list[float], label: str) -> None:
    n = len(e)
    best = []
    s = 8.0
    while s <= 13.0:
        re = im_ = 0.0
        wsum = 0.0
        for x, wgt in enumerate(e):
            if wgt <= 0:
                continue
            ang = 2 * math.pi * x / s
            re += wgt * math.cos(ang)
            im_ += wgt * math.sin(ang)
            wsum += wgt
        mag = (re * re + im_ * im_) ** 0.5 / max(1.0, wsum)
        phi = (-cmath.phase(complex(re, im_)) * s / (2 * math.pi)) % s
        best.append((mag, s, phi))
        s += 0.01
    best.sort(reverse=True)
    print(f"{label}: top lattice fits (phasor fraction, block, phase):")
    for mag, s, phi in best[:8]:
        print(f"   {mag:.4f}  block {s:.2f}px  phase {phi:.2f}   (cells across 1254: {1254/s:.2f})")


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    fit(edge_profile(im, "x"), "x axis")
    fit(edge_profile(im, "y"), "y axis")


if __name__ == "__main__":
    main()
