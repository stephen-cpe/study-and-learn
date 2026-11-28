"""Rasterize raster.png onto a logical working grid and test detail preservation.

Tests the 72x72 canvas first (as instructed). Measures whether the dark wrist band
and the gripper jaw notch survive the rasterization. Emits:
  source/_grid_test_<N>.png    sprite at 1:1 (scaled up for viewing)
  source/_grid_test_<N>_annot.png  with coordinate ticks for landmark picking
"""
from PIL import Image
import numpy as np
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, 'raster.png')

# fixed palette derived from the artwork (fixed across frames; cue ramps live in palette.json)
PALETTE = [
    (0x0b, 0x0d, 0x16),  # 0 near-black outline / faceplate
    (0x14, 0x1c, 0x30),  # 1 deep navy
    (0x2a, 0x35, 0x52),  # 2 dark steel
    (0x3b, 0x54, 0x73),  # 3 steel blue mid
    (0x5b, 0x74, 0x95),  # 4 steel blue light
    (0x7d, 0x97, 0xba),  # 5 steel blue pale
    (0xa8, 0xc0, 0xdc),  # 6 rim light
    (0x46, 0x51, 0x6d),  # 7 violet gray
    (0x67, 0x74, 0x8f),  # 8 violet gray light
    (0x36, 0x40, 0x5a),  # 9 violet gray dark
    (0x11, 0x18, 0x27),  # 10 wrist dark / faceplate 2
    (0x25, 0x30, 0x49),  # 11 wrist mid
    (0x6a, 0x7c, 0x8c),  # 12 silver shadow
    (0xb2, 0xb6, 0xb8),  # 13 silver mid
    (0xe6, 0xe7, 0xe4),  # 14 silver light
    (0xf6, 0xf7, 0xf3),  # 15 silver highlight
    (0xc9, 0x82, 0x63),  # 16 terracotta shadow
    (0xd9, 0x97, 0x74),  # 17 terracotta mid
    (0xef, 0xb2, 0x8a),  # 18 terracotta light
    (0x2c, 0x6b, 0x64),  # 19 teal dark
    (0x3f, 0x87, 0x7e),  # 20 teal mid
    (0x5a, 0xa3, 0x97),  # 21 teal light
    (0x9c, 0xd6, 0xcc),  # 22 teal pale
    (0xd3, 0xf0, 0xea),  # 23 teal highlight
    (0x0a, 0xb0, 0x0f),  # 24 eye green mid
    (0x66, 0xd7, 0x14),  # 25 eye green light
    (0x0d, 0x86, 0x0a),  # 26 eye green dark
    (0xf7, 0xf7, 0xf2),  # 27 white (catchlight)
    (0xd9, 0xbf, 0x92),  # 28 lamp tan
    (0x4f, 0x93, 0x8d),  # 29 lamp teal
    (0xe0, 0x92, 0x72),  # 30 lamp salmon
]


def load_native():
    im = Image.open(SRC).convert('RGBA')
    a = np.array(im).astype(np.int16)
    al = a[..., 3].copy()
    al[al < 128] = 0
    al[al >= 128] = 255
    a[..., 3] = al
    return a


def snap(colors):
    pal = np.array(PALETTE, np.int16)
    d = ((colors[:, None, :].astype(np.int32) - pal[None, :, :]) ** 2).sum(axis=2)
    return d.argmin(axis=1)


def rasterize(a, N, H, ground_y):
    """Nearest/median resample of the native art onto an N x N grid.

    The character (content bbox) is scaled to H logical px tall, soles on ground_y,
    centered horizontally. Each cell takes the median of its central native pixels.
    """
    al = a[..., 3]
    ys, xs = np.nonzero(al > 0)
    nx0, nx1, ny0, ny1 = xs.min(), xs.max(), ys.min(), ys.max()
    nat_h = ny1 - ny0 + 1
    nat_w = nx1 - nx0 + 1
    s = H / nat_h                      # logical px per native px
    w_logical = nat_w * s
    x_off = (N - w_logical) / 2.0      # left edge of char in logical px
    y_top = ground_y + 1 - H           # top row of char in logical px

    out_idx = np.full((N, N), -1, np.int32)
    out_a = np.full((N, N), 255, np.uint8)
    # precompute palette snaps for the whole native image
    flat = a[..., :3].reshape(-1, 3)
    snapped = snap(flat).reshape(a.shape[:2])

    for j in range(N):
        for i in range(N):
            # logical cell (i,j) covers native rect
            fx0 = nx0 + (i - x_off) / s
            fx1 = nx0 + (i + 1 - x_off) / s
            fy0 = ny0 + (j - y_top) / s
            fy1 = ny0 + (j + 1 - y_top) / s
            cx0 = int(np.ceil(fx0 + 0.2 * (fx1 - fx0)))
            cx1 = int(np.floor(fx1 - 0.2 * (fx1 - fx0)))
            cy0 = int(np.ceil(fy0 + 0.2 * (fy1 - fy0)))
            cy1 = int(np.floor(fy1 - 0.2 * (fy1 - fy0)))
            cx0, cy0 = max(cx0, 0), max(cy0, 0)
            cx1, cy1 = min(cx1, a.shape[1]), min(cy1, a.shape[0])
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            patch = snapped[cy0:cy1, cx0:cx1]
            patch_a = al[cy0:cy1, cx0:cx1]
            vals, counts = np.unique(patch[patch_a > 0], return_counts=True)
            if len(vals) == 0 or counts.max() < 0.45 * patch_a.size:
                continue
            out_idx[j, i] = vals[np.argmax(counts)]
    rgb = np.zeros((N, N, 3), np.uint8)
    ok = out_idx >= 0
    rgb[ok] = np.array(PALETTE, np.uint8)[out_idx[ok]]
    rgba = np.dstack([rgb, np.where(ok, 255, 0).astype(np.uint8)])
    return rgba, out_idx


def index_to_rgba(idx):
    rgb = np.zeros(idx.shape + (3,), np.uint8)
    ok = idx >= 0
    rgb[ok] = np.array(PALETTE, np.uint8)[idx[ok]]
    return np.dstack([rgb, np.where(ok, 255, 0).astype(np.uint8)])
