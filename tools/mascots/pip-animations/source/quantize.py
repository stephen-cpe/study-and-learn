"""Derive Pip's clean palette from pip.png and build quantized working-grid bases.

Run:  python quantize.py
Writes:
  source/palette.json          canonical palette (edit here to recolor)
  source/_diag/base_s<N>.png   quantized sprite at scale N (1x and 3x zoom)
  source/_diag/palette.png     palette swatches
"""
import os, json
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "pip.png")
DIAG = os.path.join(HERE, "_diag")
os.makedirs(DIAG, exist_ok=True)

im = Image.open(SRC).convert("RGBA")
arr = np.array(im).astype(np.float64)
H, W = arr.shape[:2]
rgb, alpha = arr[..., :3], arr[..., 3]
solid = alpha > 128

# ---------------------------------------------------------------- palette
# Seed centers observed in the sprite, then refine with a few k-means passes.
SEEDS = [
    ("outline_dark", (12, 14, 25)),    # silhouette outline + faceplate
    ("plate_dark",   (7, 11, 14)),     # pupil interior (slightly deeper)
    ("blue_mid",     (77, 108, 161)),  # main body blue
    ("blue_shade",   (67, 97, 150)),   # shaded blue (tail flank, far side)
    ("blue_deep",    (51, 77, 125)),   # deepest blue (legs)
    ("blue_pale",    (127, 168, 220)), # belly
    ("blue_light",   (150, 197, 249)), # head top-left highlight
    ("mint",         (131, 245, 171)), # eyes
    ("orange",       (253, 145, 83)),  # cheek square
    ("ivory",        (253, 244, 210)), # tooth
    ("white",        (253, 253, 253)), # catchlights
    ("gray",         (93, 95, 112)),   # neck bolt
]
names = [n for n, _ in SEEDS]
centers = np.array([c for _, c in SEEDS], dtype=np.float64)

pts = rgb[solid]
# subsample for speed
rng = np.random.default_rng(7)
if len(pts) > 250000:
    pts = pts[rng.choice(len(pts), 250000, replace=False)]

for _ in range(10):
    d = ((pts[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    lab = d.argmin(axis=1)
    for k in range(len(centers)):
        sel = pts[lab == k]
        if len(sel):
            centers[k] = sel.mean(axis=0)

# count coverage on the full solid set
d = ((rgb[solid][:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
lab = d.argmin(axis=1)
counts = np.bincount(lab, minlength=len(centers))

palette = {}
print("refined palette:")
for k, n in enumerate(names):
    c = tuple(int(round(v)) for v in centers[k])
    palette[n] = list(c)
    print(f"  {n:12s} rgb{c}  px={int(counts[k])}")

json.dump(palette, open(os.path.join(HERE, "palette.json"), "w"), indent=1)

# ---------------------------------------------------------------- bases
NX0, NY0, CELL = 256, 43, 6      # native origin + working cell size (see rig.json)
CW, CH = 128, 192                # working canvas

def quantize_base(scale, nx0, ny0, cw, ch):
    """Box-downsample pip.png by `scale` (native px per working cell) on the grid
    anchored at (nx0, ny0), quantize to the palette. Returns RGB uint8 + alpha."""
    out_rgb = np.zeros((ch, cw, 3), np.uint8)
    out_a = np.zeros((ch, cw), bool)
    flat = centers
    for cy in range(ch):
        y0 = ny0 + cy * scale
        if y0 >= H or y0 + scale <= 0:
            continue
        for cx in range(cw):
            x0 = nx0 + cx * scale
            if x0 >= W or x0 + scale <= 0:
                continue
            ya, yb = max(0, y0), min(H, y0 + scale)
            xa, xb = max(0, x0), min(W, x0 + scale)
            block = arr[ya:yb, xa:xb]
            a = block[..., 3]
            m = a > 128
            if not m.any():
                continue
            mean = block[..., :3][m].mean(axis=0)
            k = ((flat - mean) ** 2).sum(axis=1).argmin()
            out_rgb[cy, cx] = flat[k].round().astype(np.uint8)
            out_a[cy, cx] = True
    return out_rgb, out_a

for s in (5, 6, 8):
    nx0 = 304 - 8 * s
    ny0 = 151 - 18 * s
    cw, ch = 128, 192 if s == 6 else (108, 160)
    if s == 5:
        cw, ch = 152, 228
    if s == 8:
        cw, ch = 96, 144
    o_rgb, o_a = quantize_base(s, nx0, ny0, cw, ch)
    out = np.dstack([o_rgb, np.where(o_a, 255, 0).astype(np.uint8)])
    img = Image.fromarray(out, "RGBA")
    img.save(os.path.join(DIAG, f"base_s{s}.png"))
    for zoom in (3, 6):
        z = img.resize((img.width * zoom, img.height * zoom), Image.NEAREST)
        bg = Image.new("RGBA", z.size, (255, 255, 255, 255))
        bg.alpha_composite(z)
        bg.convert("RGB").save(os.path.join(DIAG, f"base_s{s}_{zoom}x.png"))
    print(f"scale s={s}: cell={s}px native, canvas {cw}x{ch}, "
          f"solid cells {int(o_a.sum())}")

# palette swatch strip
sw = Image.new("RGB", (len(names) * 40, 40))
for k, n in enumerate(names):
    c = tuple(palette[n])
    for x in range(40):
        for y in range(40):
            sw.putpixel((k * 40 + x, y), c)
sw.save(os.path.join(DIAG, "palette.png"))
print("done")
