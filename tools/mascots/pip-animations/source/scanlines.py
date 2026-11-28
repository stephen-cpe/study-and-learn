"""Run-length scanlines of pip.png to reveal block structure.

Usage: python scanlines.py [row y ...] [--col x ...]
Defaults: a few informative rows/cols.
"""
import sys, os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "pip.png")
if len(sys.argv) > 1:
    SRC = sys.argv[1]

im = Image.open(SRC).convert("RGBA")
a = np.array(im).astype(int)
rgb, alpha = a[..., :3], a[..., 3]
H, W = a.shape[:2]

def qcolor(px):
    r, g, b, al = px
    if al <= 128:
        return "...."
    return f"{r//1},{g//1},{b//1}"

def runs_line(line, axis_name):
    out = []
    cur, start = None, 0
    for i, px in enumerate(line):
        # quantize color to nearest 12 to merge noise
        key = tuple((np.array(px[:3]) // 14).tolist()) if px[3] > 128 else "T"
        if key != cur:
            if cur is not None:
                out.append((start, i - 1, cur, i - start))
            cur, start = key, i
    out.append((start, len(line) - 1, cur, len(line) - start))
    print(f"{axis_name}:")
    for s, e, c, n in out:
        if n < 3:
            continue
        px = line[s]
        print(f"   {s:5d}..{e:5d} len {n:5d}  {qcolor(px)}")
    print()

rows = [557, 404, 350, 613, 712, 900, 1050]
cols = [538, 678, 460, 700]
if len(sys.argv) > 2:
    rows = [int(v) for v in sys.argv[1:]]

for y in rows:
    runs_line(a[y], f"row y={y}")
for x in cols:
    runs_line(a[:, x], f"col x={x}")
