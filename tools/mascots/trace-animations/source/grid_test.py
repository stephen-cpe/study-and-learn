"""Recover the working pixel grid of trace.png by testing candidate block grids.

For each candidate grid G (block size = 1254/G, possibly fractional), box-sample
the source onto the grid, measure how flat each block is and how few colors the
grid needs.  A true pixel-art upscale scores far better than wrong grids.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"
OUT = Path(__file__).resolve().parent / "_probe"
OUT.mkdir(exist_ok=True)


def sample_grid(im: Image.Image, g: int, off: float = 0.5) -> Image.Image:
    """Box-sample the (blurred) image onto a g x g grid; return RGB preview."""
    w, h = im.size
    sm = im.resize((g, g), Image.BOX)  # area average
    return sm


def score(im: Image.Image, g: int) -> tuple[float, float, Image.Image]:
    w, h = im.size
    s = w / g
    px = im.load()
    flat_err = 0.0
    total = 0
    grid = Image.new("RGBA", (g, g))
    gp = grid.load()
    for gy in range(g):
        y0, y1 = int(round(gy * s)), max(int(round(gy * s)) + 1, int(round((gy + 1) * s)))
        for gx in range(g):
            x0, x1 = int(round(gx * s)), max(int(round(gx * s)) + 1, int(round((gx + 1) * s)))
            rs = gs = bs = as_ = 0
            n = 0
            for y in range(y0, min(y1, h)):
                for x in range(x0, min(x1, w)):
                    r, g_, b, a = px[x, y]
                    rs += r; gs += g_; bs += b; as_ += a
                    n += 1
            if not n:
                continue
            mr, mg, mb, ma = rs / n, gs / n, bs / n, as_ / n
            gp[gx, gy] = (int(mr), int(mg), int(mb), int(ma))
            for y in range(y0, min(y1, h)):
                for x in range(x0, min(x1, w)):
                    r, g_, b, a = px[x, y]
                    flat_err += abs(r - mr) + abs(g_ - mg) + abs(b - mb) + abs(a - ma)
                    total += 1
    return flat_err / max(1, total), 0.0, grid


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    for g in (64, 72, 84, 96, 104, 114, 126, 128, 136, 152, 168, 209):
        err, _, grid = score(im, g)
        grid.resize((g * 4, g * 4), Image.NEAREST).save(OUT / f"grid_{g}.png")
        print(f"grid {g:4d} (block {1254/g:6.2f}px): mean |block err| = {err:6.2f}")


if __name__ == "__main__":
    main()
