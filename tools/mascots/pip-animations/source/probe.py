"""Probe small features in pip.png to measure the underlying block size."""
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

def bbox(mask, label):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        print(f"{label}: none")
        return None
    # split into connected components (4-connectivity) with simple labeling
    from collections import deque
    seen = np.zeros(mask.shape, bool)
    comps = []
    pts = list(zip(*np.nonzero(mask)))
    idx = {p: i for i, p in enumerate(pts)}
    for p in pts:
        if seen[p]:
            continue
        q = deque([p]); seen[p] = True; comp = []
        while q:
            cy, cx = q.popleft(); comp.append((cy, cx))
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = cy+dy, cx+dx
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; q.append((ny, nx))
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    print(f"{label}: {len(comps)} component(s)")
    for comp in comps[:6]:
        ys = [p[0] for p in comp]; xs = [p[1] for p in comp]
        print(f"   n={len(comp):5d}  x {min(xs)}..{max(xs)} (w {max(xs)-min(xs)+1})  "
              f"y {min(ys)}..{max(ys)} (h {max(ys)-min(ys)+1})")
    return comps

r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
solid = alpha > 128

# white catchlights (near-white)
bbox(solid & (r > 200) & (g > 200) & (b > 200), "white catchlights")
# ivory tooth (warm white)
bbox(solid & (r > 200) & (g > 200) & (b > 150) & (b < 230) & (r >= g - 10), "ivory tooth?")
# orange cheek
bbox(solid & (r > 200) & (g > 80) & (g < 180) & (b < 130), "orange cheek")
# mint eyes
bbox(solid & (g > 180) & (r < 200) & (b > 120) & (b < 220) & (g - r > 40), "mint eyes")
# gray neck (neutral gray)
bbox(solid & (abs(r-g) < 18) & (abs(g-b) < 18) & (r > 60) & (r < 160), "gray neck")
# darkest (outline / faceplate)
m = solid & (r < 30) & (g < 30) & (b < 45)
ys, xs = np.nonzero(m)
print(f"dark pixels: {m.sum()}  bbox x {xs.min()}..{xs.max()} y {ys.min()}..{ys.max()}")
