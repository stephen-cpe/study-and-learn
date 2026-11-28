"""Analyze trace.png: alpha bounds, pixel block size, palette, feature regions.

Run:  python trace-animations/source/analyze.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    print(f"size: {w} x {h}  mode: {im.mode}")

    px = im.load()
    alpha = im.split()[3]
    bbox = alpha.getbbox()
    print(f"alpha bbox: {bbox}  (visible {bbox[2]-bbox[0]} x {bbox[3]-bbox[1]})")

    # distinct colors (RGB of pixels with alpha > 0) and alpha values
    colors = Counter()
    alphas = Counter()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            alphas[a] += 1
            if a:
                colors[(r, g, b)] += 1
    print(f"alpha values: {dict(sorted(alphas.items()))}")
    print(f"distinct opaque colors: {len(colors)}")
    for c, n in colors.most_common(40):
        print(f"  {c}  #{c[0]:02x}{c[1]:02x}{c[2]:02x}  x{n}")

    # ---- detect pixel block size -------------------------------------------
    # A pixel-art upscale has all color/alpha transitions aligned to a grid of
    # block size S with offset (ox, oy): every column/row where the image
    # changes must share one residue class modulo S.
    # column transitions
    col_t = []
    for x in range(1, w):
        a = [px[x, y] for y in range(h)]
        b = [px[x - 1, y] for y in range(h)]
        if a != b:
            col_t.append(x)
    row_t = []
    for y in range(1, h):
        a = [px[x, y] for x in range(w)]
        b = [px[x, y - 1] for x in range(w)]
        if a != b:
            row_t.append(y)
    print(f"column transitions: {len(col_t)}  first: {col_t[:12]}")
    print(f"row transitions: {len(row_t)}  first: {row_t[:12]}")

    # candidate block sizes: all divisors of the transition spacing gcd-ish
    diffs = [col_t[i + 1] - col_t[i] for i in range(len(col_t) - 1)]
    from math import gcd
    from functools import reduce
    g = reduce(gcd, [d for d in diffs if d > 0]) if diffs else 1
    print(f"gcd of column transition gaps: {g}")
    diffs_r = [row_t[i + 1] - row_t[i] for i in range(len(row_t) - 1)]
    gr = reduce(gcd, [d for d in diffs_r if d > 0]) if diffs_r else 1
    print(f"gcd of row transition gaps: {gr}")

    # verify a block size: every transition lies on the same residue class mod S
    def verify(trans: list[int], s: int) -> bool:
        if not trans:
            return True
        r = trans[0] % s
        return all(t % s == r for t in trans)

    best = None
    for s in range(2, 33):
        if verify(col_t, s) and verify(row_t, s):
            best = s
    # prefer the largest plausible block size
    candidates = [s for s in range(2, 65) if verify(col_t, s) and verify(row_t, s)]
    print(f"block-size candidates (aligned on both axes): {candidates}")
    if candidates:
        s = max(candidates)
        ox = col_t[0] % s if col_t else 0
        oy = row_t[0] % s if row_t else 0
        print(f"chosen block size: {s}  offset: ({ox}, {oy})")
        gw = (w - ox + s - 1) // s
        gh = (h - oy + s - 1) // s
        print(f"working grid: {gw} x {gh}")
        # sample block colors to confirm uniformity
        bad = 0
        grid = {}
        for gy in range(gh):
            for gx in range(gw):
                block = Counter()
                for y in range(oy + gy * s, min(oy + gy * s + s, h)):
                    for x in range(ox + gx * s, min(ox + gx * s + s, w)):
                        block[px[x, y]] += 1
                mc, n = block.most_common(1)[0]
                if n != sum(block.values()):
                    bad += 1
                grid[(gx, gy)] = mc
        print(f"non-uniform blocks: {bad} / {gw*gh}")


if __name__ == "__main__":
    main()
