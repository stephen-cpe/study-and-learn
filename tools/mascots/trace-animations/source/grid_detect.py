"""Measure stair-step run lengths to recover the underlying pixel grid."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    # blur to kill generation noise, keep the stair structure
    sm = im.filter(ImageFilter.GaussianBlur(1.2))
    px = sm.load()

    def q(c, tol=18):
        return (c[0] // tol, c[1] // tol, c[2] // tol, c[3] // 40)

    runs_x = Counter()
    for y in range(0, h, 3):
        run = 1
        prev = q(px[0, y])
        for x in range(1, w):
            cur = q(px[x, y])
            if cur == prev:
                run += 1
            else:
                runs_x[run] += 1
                run = 1
                prev = cur
        runs_x[run] += 1

    runs_y = Counter()
    for x in range(0, w, 3):
        run = 1
        prev = q(px[x, 0])
        for y in range(1, h):
            cur = q(px[x, y])
            if cur == prev:
                run += 1
            else:
                runs_y[run] += 1
                run = 1
                prev = cur
        runs_y[run] += 1

    def show(name, runs):
        print(f"{name}: top run lengths")
        for r, n in runs.most_common(25):
            print(f"  len {r:4d}  x{n}")

    show("rows (x-runs)", runs_x)
    show("cols (y-runs)", runs_y)

    # transition x positions after coarse blur; find step lattice by scoring
    edges_x = []
    for x in range(1, w):
        d = 0
        for y in range(0, h, 6):
            a, b = px[x, y], px[x - 1, y]
            d += abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
        if d > 900:
            edges_x.append(x)
    print(f"strong x edges: {len(edges_x)}  sample {edges_x[:20]}")
    gaps = Counter(edges_x[i + 1] - edges_x[i] for i in range(len(edges_x) - 1))
    print("gap histogram (x edges):", sorted(gaps.items())[:20])

    best = []
    for s in range(4, 25):
        for off in range(s):
            hits = sum(1 for e in edges_x if (e - off) % s == 0)
            best.append((hits / max(1, len(edges_x)), s, off))
    best.sort(reverse=True)
    print("lattice fit for x edges (fraction, period, offset):", best[:8])


if __name__ == "__main__":
    main()
