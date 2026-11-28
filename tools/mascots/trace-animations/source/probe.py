"""Probe trace.png pixel structure: magnified crops + edge periodicity."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"
OUT = Path(__file__).resolve().parent / "_probe"
OUT.mkdir(exist_ok=True)


def crops() -> None:
    im = Image.open(SRC).convert("RGBA")
    # regions of interest (full-res coords)
    regions = {
        "eye_left_edge": (330, 300, 430, 400),   # stair-step edge of left eye
        "pupil": (430, 280, 570, 420),            # pupil + catchlight
        "led_collar": (700, 580, 880, 760),       # collar + status light
        "brow": (300, 130, 560, 280),             # left eyebrow
        "loop_bottom": (300, 950, 950, 1254),     # bottom of outer loop
    }
    for name, box in regions.items():
        c = im.crop(box)
        c.resize((c.width * 6, c.height * 6), Image.NEAREST).save(OUT / f"{name}.png")
        print(f"wrote {name}.png  ({box})")


def periodicity() -> None:
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    # blur slightly to kill noise, then measure edge strength along x and y
    rgb = im.convert("RGB").filter(ImageFilter.GaussianBlur(2))
    px = rgb.load()

    ex = [0.0] * w
    for x in range(1, w):
        s = 0.0
        for y in range(0, h, 4):
            a, b = px[x, y], px[x - 1, y]
            s += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
        ex[x] = s
    ey = [0.0] * h
    for y in range(1, h):
        s = 0.0
        for x in range(0, w, 4):
            a, b = px[x, y], px[x, y - 1]
            s += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
        ey[y] = s

    def best_period(e, n, lo=2, hi=40):
        scores = []
        for s in range(lo, hi + 1):
            for off in range(s):
                tot = 0.0
                for i in range(off, n, s):
                    tot += e[i]
                scores.append((tot, s, off))
        scores.sort(reverse=True)
        return scores[:6]

    print("x-edge period candidates (score, period, offset):")
    for t in best_period(ex, w):
        print("  ", t)
    print("y-edge period candidates (score, period, offset):")
    for t in best_period(ey, h):
        print("  ", t)


if __name__ == "__main__":
    crops()
    periodicity()
