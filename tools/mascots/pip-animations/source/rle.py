"""Exact run-length dump of the quantized grid for precise mask design.

Usage: python rle.py y0 y1 [x0 x1]
"""
import os, sys, json
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
palette = json.load(open(os.path.join(HERE, "palette.json")))
names = list(palette)
centers = np.array([palette[n] for n in names], float)
CH = {"outline_dark": "#", "plate_dark": "@", "blue_mid": "B", "blue_shade": "b",
      "blue_deep": "d", "blue_pale": "P", "blue_light": "L", "mint": "M",
      "orange": "O", "ivory": "I", "white": "W", "gray": "G"}

img = np.array(Image.open(os.path.join(HERE, "_diag", "base_s6.png")).convert("RGBA"))
rgb, a = img[..., :3].astype(float), img[..., 3]
labels = np.zeros(img.shape[:2], "U1")
for y in range(img.shape[0]):
    for x in range(img.shape[1]):
        labels[y, x] = "." if a[y, x] == 0 else CH[names[((centers - rgb[y, x]) ** 2).sum(1).argmin()]]

y0, y1 = int(sys.argv[1]), int(sys.argv[2])
x0, x1 = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (0, img.shape[1])
for y in range(y0, min(y1, img.shape[0])):
    runs = []
    cur = labels[y, x0]; start = x0
    for x in range(x0 + 1, x1):
        if labels[y, x] != cur:
            runs.append((start, x - 1, cur))
            cur, start = labels[y, x], x
    runs.append((start, x1 - 1, cur))
    txt = "  ".join(f"{s}-{e}{c}" if s != e else f"{s}{c}" for s, e, c in runs if c != "." or e - s >= 3)
    print(f"{y:4d}: {txt}")
