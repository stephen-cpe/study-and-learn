"""Analyze pip.png: alpha bounds, underlying pixel lattice, palette.

Run:  python analyze.py [path/to/pip.png]
Prints a report and writes lattice/palette diagnostics into source/_diag/.
"""
import sys, os, json
from collections import Counter
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "pip.png")
if len(sys.argv) > 1:
    SRC = sys.argv[1]
DIAG = os.path.join(HERE, "_diag")
os.makedirs(DIAG, exist_ok=True)

im = Image.open(SRC).convert("RGBA")
arr = np.array(im).astype(np.int32)
H, W = arr.shape[:2]
alpha = arr[..., 3]
print(f"file: {os.path.abspath(SRC)}")
print(f"size: {W}x{H}  mode: RGBA")

# --- visible bounds (alpha>8 ignores the faint noise halo) ---
ys, xs = np.nonzero(alpha > 8)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
print(f"alpha>8 bounds: x {x0}..{x1} (w {x1-x0+1})  y {y0}..{y1} (h {y1-y0+1})")
ys, xs = np.nonzero(alpha > 128)
print(f"alpha>128 bounds: x {xs.min()}..{xs.max()}  y {ys.min()}..{ys.max()}")
print(f"alpha: min {alpha.min()} max {alpha.max()}  frac==0 {(alpha==0).mean():.3f}  "
      f"frac<=8 {((alpha>0)&(alpha<=8)).mean():.4f}  frac>=250 {(alpha>=250).mean():.3f}")

rgb = arr[..., :3]
coldiff = np.abs(np.diff(rgb, axis=1)).sum(axis=(0, 2)).astype(float) \
    + np.abs(np.diff(alpha, axis=1)).sum(axis=0) * 4.0
rowdiff = np.abs(np.diff(rgb, axis=0)).sum(axis=(1, 2)).astype(float) \
    + np.abs(np.diff(alpha, axis=0)).sum(axis=1) * 4.0

def fit_lattice(profile, lo, hi, span):
    """Find (period, phase) whose grid lines best align with profile energy.
    profile[i] is the change between pixel i and i+1 -> edge at i+0.5."""
    n = len(profile)
    best = None
    for p in np.arange(lo, hi, 0.02):
        for o in np.arange(0.0, p, 0.25):
            # grid line positions o + k*p within the content span
            ks = np.arange(np.floor((span[0] - o) / p), np.ceil((span[1] - o) / p) + 1)
            pos = o + ks * p
            pos = pos[(pos > 1) & (pos < n - 1)]
            if len(pos) < 8:
                continue
            i0 = np.floor(pos - 1).astype(int)
            frac = pos - 1 - i0
            # sample profile with linear interp over ±1 px
            v = (profile[np.clip(i0, 0, n-1)] * (1 - frac) + profile[np.clip(i0+1, 0, n-1)] * frac
                 + profile[np.clip(i0+1, 0, n-1)] * (1 - frac) + profile[np.clip(i0+2, 0, n-1)] * frac) / 2
            score = v.mean() / (profile.mean() + 1e-9)
            if best is None or score > best[0]:
                best = (score, p, o, len(pos))
    return best

print("\nlattice fit (columns):")
bc = fit_lattice(coldiff, 18, 40, (x0, x1 + 1))
print(f"  period {bc[1]:.2f} phase {bc[2]:.2f} score {bc[0]:.3f} lines {bc[3]}")
print("lattice fit (rows):")
br = fit_lattice(rowdiff, 18, 40, (y0, y1 + 1))
print(f"  period {br[1]:.2f} phase {br[2]:.2f} score {br[0]:.3f} lines {br[3]}")

# how many blocks does content span?
for name, b, span in (("x", bc, (x0, x1 + 1)), ("y", br, (y0, y1 + 1))):
    p, o = b[1], b[2]
    nblk = (span[1] - span[0]) / p
    print(f"  {name} span {span[1]-span[0]} px = {nblk:.2f} blocks (period {p:.2f})")

# --- palette: round the color clouds ---
flat = rgb[alpha > 128].reshape(-1, 3)
q = (flat // 8) * 8
key = q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2]
cnt = Counter(key.tolist())
print("\ntop quantized colors (bucketed by 8):")
palette_guess = []
for k, n in cnt.most_common(14):
    r, g, b = k // 65536, (k // 256) % 256, k % 256
    sel = np.all(q == np.array([r, g, b]), axis=1)
    mean = flat[sel].mean(axis=0)
    print(f"  rgb{tuple(int(v) for v in mean)}  n={n}")
    palette_guess.append([int(v) for v in np.round(mean)])

json.dump({
    "size": [W, H],
    "bounds_alpha8": [int(x0), int(y0), int(x1), int(y1)],
    "lattice_x": {"period": bc[1], "phase": bc[2], "score": bc[0]},
    "lattice_y": {"period": br[1], "phase": br[2], "score": br[0]},
    "palette_guess": palette_guess,
}, open(os.path.join(DIAG, "analysis.json"), "w"), indent=1)
print(f"\nwrote {os.path.join(DIAG, 'analysis.json')}")
