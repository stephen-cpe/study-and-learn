"""Working-grid test (run before choosing the canvas size).

Rasterizes the artwork at the previous pack's 72x72 canvas and at the candidate 96x96,
then measures whether two fine details survive at 1:1:
  * the dark wrist band between the silver forearm and the terracotta gripper
  * the notch (gap) between the two gripper jaws
The result documents the canvas choice in README.md.
"""
from PIL import Image, ImageDraw
import numpy as np
import os

from rasterize import load_native, rasterize, index_to_rgba, PALETTE

HERE = os.path.dirname(os.path.abspath(__file__))

# palette index groups
TERRA = (16, 17, 18)
SILVER = (13, 14, 15)
WRIST = (10, 11, 0)


def measure(idx, tag):
    terra = np.isin(idx, TERRA)
    ys, xs = np.nonzero(terra)
    if len(xs) == 0:
        print('  [%s] no gripper found' % tag)
        return None
    xm = xs.max()
    sel = xs > xm - 18          # viewer's right gripper cluster
    gx0, gx1 = xs[sel].min(), xs[sel].max()
    gy0, gy1 = ys[sel].min(), ys[sel].max()
    prof = []
    for x in range(gx0, gx1 + 1):
        col = np.nonzero(terra[:, x])[0]
        col = col[(col >= gy0) & (col <= gy1)]
        prof.append(col.max() if len(col) else gy0)
    prof = np.array(prof)
    gap = prof.max() - prof
    notch_w = notch_depth = 0
    cols = np.nonzero(gap >= 1)[0]
    if len(cols):
        runs, start, prev = [], cols[0], cols[0]
        for c in cols[1:]:
            if c > prev + 1:
                runs.append((start, prev))
                start = c
            prev = c
        runs.append((start, prev))
        interior = [r for r in runs if r[0] > gx0 and r[1] < gx1]
        if interior:
            w = max(r[1] - r[0] + 1 for r in interior)
            notch_w = w
            notch_depth = int(gap.max())
    # wrist: dark band between silver shell and gripper, central column
    cx = (gx0 + gx1) // 2
    wrist = 0
    col_s = np.nonzero(np.isin(idx[:, cx], SILVER))[0]
    col_t = np.nonzero(terra[:, cx])[0]
    if len(col_s) and len(col_t):
        above = col_s[col_s < gy0]
        if len(above):
            s_hi = above.max()
            t_lo = col_t.min()
            band = np.isin(idx[s_hi + 1:t_lo, cx], WRIST)
            wrist = int(band.sum())
    print('  [%-6s] gripper %2dx%2d px | notch gap %d px wide x %d deep | wrist band %d px tall'
          % (tag, gx1 - gx0 + 1, gy1 - gy0 + 1, notch_w, notch_depth, wrist))
    return notch_w, notch_depth, wrist


if __name__ == '__main__':
    a = load_native()
    results = {}
    for N, H, gy in ((72, 68, 69), (96, 90, 91)):
        rgba, idx = rasterize(a, N, H, gy)
        img = Image.fromarray(rgba)
        img.save(os.path.join(HERE, '_grid_test_%d.png' % N))
        big = img.resize((N * 6, N * 6), Image.NEAREST)
        vis = big.convert('RGBA')
        bgc = Image.new('RGBA', vis.size, (255, 255, 255, 255))
        bgc.alpha_composite(vis)
        d = ImageDraw.Draw(bgc)
        for t in range(0, N + 1, 4):
            d.line((t * 6, 0, t * 6, N * 6), fill=(255, 0, 0, 90))
            d.line((0, t * 6, N * 6, t * 6), fill=(255, 0, 0, 90))
        for t in range(0, N + 1, 8):
            d.text((t * 6 + 2, 2), str(t), fill=(255, 0, 255))
            d.text((2, t * 6 + 2), str(t), fill=(255, 0, 255))
        bgc.convert('RGB').save(os.path.join(HERE, '_grid_test_%d_annot.png' % N))
        # arm close-up at 10x for the wrist/notch jury
        arm = img.crop((N // 2, int(gy * 0.45), N, gy + 1))
        arm.resize((arm.width * 10, arm.height * 10), Image.NEAREST).convert('RGB').save(
            os.path.join(HERE, '_grid_test_%d_arm10x.png' % N))
        print('N=%d  char H=%d  ground row=%d' % (N, H, gy))
        results[N] = measure(idx, 'N=%d' % N)
    print('\nverdict:')
    for N, r in results.items():
        if r is None:
            continue
        nw, nd, w = r
        ok = nw >= 2 and nd >= 2 and w >= 2
        print('  N=%d -> %s (notch %dx%d, wrist %d)' %
              (N, 'PRESERVES wrist + notch' if ok else 'LOSES detail', nw, nd, w))
