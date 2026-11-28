"""Extract the working pixel grid from trace.png.

Measured source properties (see lattice_fit.py / lattice_alpha.py):
  * image 1254x1254 RGBA, generation noise + soft 2-3px edges
  * pixel-art staircases fit block sx=9.83px, sy=9.73px, phase (2, 2)
    (alpha-edge Fourier coherence 0.23/0.25 - AI art, so the lattice is
    approximate, but 10px-scale cells are unambiguous: contour steps are
    9.7-11px and the catchlight is only 2-3 cells wide)
  * true visible bounds (alpha >= 32): (355, 78, 860, 1196) = 505 x 1118 px
    -> ~52 x 115 cells of content

This script samples one median colour per cell (robust to the source noise and
bevel gradients), snaps colours to a compact palette that preserves the source
palette, and writes:
  grid.png        neutral pose on the working grid (128x128 cells)
  grid_4x.png     preview
  palette.json    palette colours
  compare.png     original vs nearest-upscaled extraction

Run:  python trace-animations/source/extract.py [--sx 9.83 --sy 9.73 --phx 2 --phy 2]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"
OUT = Path(__file__).resolve().parent
GRID_N = 128  # cells per axis (covers the whole 1254px source at ~9.8px/cell)


def sample_cells(im: Image.Image, sx: float, sy: float, phx: float, phy: float):
    """Median colour per cell; returns dict (gx, gy) -> (r, g, b) for opaque cells."""
    px = im.load()
    w, h = im.size
    cells = {}
    for gy in range(GRID_N):
        y0 = int(round(phy + sy * gy))
        y1 = max(y0 + 1, int(round(phy + sy * (gy + 1))))
        for gx in range(GRID_N):
            x0 = int(round(phx + sx * gx))
            x1 = max(x0 + 1, int(round(phx + sx * (gx + 1))))
            opaque = []
            total = 0
            for y in range(y0, min(y1, h)):
                for x in range(x0, min(x1, w)):
                    r, g, b, a = px[x, y]
                    total += 1
                    if a >= 128:
                        opaque.append((r, g, b))
            if total and len(opaque) * 4 >= total:  # >= 25% solid coverage
                opaque.sort(key=lambda c: c[0] + c[1] + c[2])
                n = len(opaque)
                med = opaque[n // 2] if n % 2 else tuple(
                    (opaque[n // 2 - 1][i] + opaque[n // 2][i]) // 2 for i in range(3)
                )
                cells[(gx, gy)] = med
    return cells


def build_palette(cells: dict, max_colors: int = 40, tol: int = 14) -> list[tuple[int, int, int]]:
    """Average-link clustering with a colour tolerance -> compact source palette."""
    pts = sorted(set(cells.values()))
    clusters: list[list[tuple[int, int, int]]] = []
    for c in pts:
        placed = False
        for cl in clusters:
            cx = sum(p[0] for p in cl) / len(cl)
            cy = sum(p[1] for p in cl) / len(cl)
            cz = sum(p[2] for p in cl) / len(cl)
            if abs(cx - c[0]) <= tol and abs(cy - c[1]) <= tol and abs(cz - c[2]) <= tol:
                cl.append(c)
                placed = True
                break
        if not placed:
            clusters.append([c])
    # merge smallest clusters until under max_colors
    while len(clusters) > max_colors:
        clusters.sort(key=len)
        a = clusters.pop(0)
        best_i, best_d = 0, 1e9
        for i, cl in enumerate(clusters):
            ax = sum(p[0] for p in a) / len(a)
            ay = sum(p[1] for p in a) / len(a)
            az = sum(p[2] for p in a) / len(a)
            bx = sum(p[0] for p in cl) / len(cl)
            by = sum(p[1] for p in cl) / len(cl)
            bz = sum(p[2] for p in cl) / len(cl)
            d = abs(ax - bx) + abs(ay - by) + abs(az - bz)
            if d < best_d:
                best_d, best_i = d, i
        clusters[best_i].extend(a)
    pal = []
    for cl in clusters:
        n = len(cl)
        pal.append((sum(p[0] for p in cl) // n, sum(p[1] for p in cl) // n, sum(p[2] for p in cl) // n))
    pal.sort(key=lambda c: -(c[0] + c[1] + c[2]))
    return pal


def snap(cells: dict, pal: list[tuple[int, int, int]]) -> dict:
    out = {}
    for k, c in cells.items():
        best, bd = None, 1e9
        for p in pal:
            d = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2
            if d < bd:
                bd, best = d, p
        out[k] = best
    return out


def cells_to_image(cells: dict) -> Image.Image:
    im = Image.new("RGBA", (GRID_N, GRID_N), (0, 0, 0, 0))
    px = im.load()
    for (gx, gy), c in cells.items():
        px[gx, gy] = (*c, 255)
    return im


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sx", type=float, default=9.83)
    ap.add_argument("--sy", type=float, default=9.73)
    ap.add_argument("--phx", type=float, default=2.0)
    ap.add_argument("--phy", type=float, default=2.0)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    im = Image.open(SRC).convert("RGBA")
    cells = sample_cells(im, args.sx, args.sy, args.phx, args.phy)
    print(f"opaque cells: {len(cells)}")
    xs = [gx for gx, _ in cells]
    ys = [gy for _, gy in cells]
    print(f"content cells: x {min(xs)}..{max(xs)} ({max(xs)-min(xs)+1})  "
          f"y {min(ys)}..{max(ys)} ({max(ys)-min(ys)+1})")

    pal = build_palette(cells)
    print(f"palette: {len(pal)} colours")
    for c in pal:
        print(f"   #{c[0]:02x}{c[1]:02x}{c[2]:02x}  {c}")

    snapped = snap(cells, pal)
    grid = cells_to_image(snapped)
    tag = args.tag
    grid.save(OUT / f"grid{tag}.png")
    grid.resize((GRID_N * 4, GRID_N * 4), Image.NEAREST).save(OUT / f"grid{tag}_4x.png")

    # annotated preview: 4x with red gridlines every 5 cells
    ann = grid.resize((GRID_N * 4, GRID_N * 4), Image.NEAREST).convert("RGBA")
    d = ImageDraw.Draw(ann)
    for i in range(0, GRID_N + 1, 5):
        col = (255, 60, 60, 160) if i % 10 else (255, 210, 0, 200)
        d.line([(i * 4, 0), (i * 4, GRID_N * 4)], fill=col, width=1)
        d.line([(0, i * 4), (GRID_N * 4, i * 4)], fill=col, width=1)
    ann.save(OUT / f"grid{tag}_annotated.png")

    with open(OUT / f"palette{tag}.json", "w") as f:
        json.dump([list(c) for c in pal], f, indent=2)

    # comparison: nearest-upscale extraction back to source scale, cropped to content
    recon = grid.resize((int(GRID_N * args.sx), int(GRID_N * args.sy)), Image.NEAREST)
    ox = int(args.phx)
    oy = int(args.phy)
    canvas = Image.new("RGBA", im.size, (40, 40, 48, 255))
    canvas.alpha_composite(recon, (ox, oy))
    box = (355, 78, 860, 1196)
    a = im.crop(box)
    b = canvas.crop(box)
    comp = Image.new("RGBA", (a.width * 2 + 12, a.height), (255, 0, 255, 255))
    comp.paste(a, (0, 0))
    comp.paste(b, (a.width + 12, 0))
    comp.save(OUT / f"compare{tag}.png")
    print(f"wrote grid{tag}.png, grid{tag}_4x.png, grid{tag}_annotated.png, palette{tag}.json, compare{tag}.png")


if __name__ == "__main__":
    main()
