"""Print the quantized working grid as ASCII (1 char per cell) for mask design."""
import os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "_diag", "base_s6.png")
PAL = os.path.join(HERE, "palette.json")

import json
palette = json.load(open(PAL))
names = list(palette)
centers = np.array([palette[n] for n in names], float)

img = np.array(Image.open(BASE).convert("RGBA"))
rgb, a = img[..., :3].astype(float), img[..., 3]
CH = {  # one char per palette name
    "outline_dark": "#", "plate_dark": "@", "blue_mid": "B", "blue_shade": "b",
    "blue_deep": "d", "blue_pale": "P", "blue_light": "L", "mint": "M",
    "orange": "O", "ivory": "I", "white": "W", "gray": "G",
}
rows = []
for y in range(img.shape[0]):
    line = []
    for x in range(img.shape[1]):
        if a[y, x] == 0:
            line.append(".")
        else:
            k = ((centers - rgb[y, x]) ** 2).sum(axis=1).argmin()
            line.append(CH[names[k]])
    rows.append("".join(line))

y0, y1 = 0, len(rows)
if len(os.sys.argv) > 2:
    y0, y1 = int(os.sys.argv[1]), int(os.sys.argv[2])
print("     " + "".join(str(x // 10 % 10) for x in range(len(rows[0]))))
print("     " + "".join(str(x % 10) for x in range(len(rows[0]))))
for y in range(y0, y1):
    print(f"{y:4d} {rows[y]}")
