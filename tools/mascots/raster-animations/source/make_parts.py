"""Cut raster.png into editable rig parts on the 96x96 working grid.

Outputs (all editable PNGs, 1:1 logical pixels):
  parts/base.png        torso + hips + legs + boots (arms and head removed)
  parts/head.png        CRT shell + faceplate + bezel + ear caps (eyes cut out)
  parts/antenna.png     mast + bulb (travels with head; own light mask)
  parts/eyeL.png eyeR.png        movable eyes (green + catchlight)
  parts/shoulderL.png shoulderR.png   teal ball joints (static anchors)
  parts/chainL.png chainR.png   moving arm chain at rest (upper+forearm+wrist+gripper)
  parts/seg_upperL/R.png seg_foreL/R.png seg_wristL/R.png seg_gripL/R.png  chain sub-parts
  parts/mask_*.png      light masks (eyes, antenna bulb, chest lamps)
  parts.json            rects, pivots, anchors, ground line, canvas
  palette.json          fixed palette + signal cue ramps

The moving chains are cut OUT of base/head so the neutral hands disappear from
their original locations when a chain is redrawn at a raised pose.
"""
from PIL import Image
import numpy as np
import json
import os

from rasterize import load_native, rasterize, index_to_rgba, PALETTE

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(HERE, 'parts')
os.makedirs(PARTS, exist_ok=True)

N, H, GROUND = 96, 90, 91

# palette index groups
DARK = (0, 1, 2, 9, 10, 11)
STEEL = (3, 4, 5, 6)
VIOLET = (7, 8)
SILVER = (12, 13, 14, 15, 27)
TERRA = (16, 17, 18, 30)      # 30 = salmon: chest lamp + gripper top row in this export
TEAL = (19, 20, 21, 22, 23, 29)
GREEN = (24, 25, 26)
WHITE = (15, 27)              # eye catchlight exports as 15 in this artwork
LAMP = (28, 29, 30)


def clusters(mask, gap=2):
    """Split a boolean mask into row-major bbox clusters (simple flood fill)."""
    ys, xs = np.nonzero(mask)
    pts = set(zip(ys.tolist(), xs.tolist()))
    out = []
    while pts:
        seed = pts.pop()
        stack = [seed]
        comp = [seed]
        while stack:
            y, x = stack.pop()
            for dy in range(-gap, gap + 1):
                for dx in range(-gap, gap + 1):
                    q = (y + dy, x + dx)
                    if q in pts:
                        pts.remove(q)
                        stack.append(q)
                        comp.append(q)
        cys, cxs = zip(*comp)
        out.append((min(cxs), max(cxs), min(cys), max(cys), len(comp)))
    out.sort(key=lambda r: (r[2], r[0]))
    return out


def cut(idx, rect):
    x0, x1, y0, y1 = rect
    return idx[y0:y1 + 1, x0:x1 + 1].copy()


def full(idx_crop, rect):
    """Embed a cropped part back into a full 96x96 grid (-1 elsewhere)."""
    out = np.full((N, N), -1, np.int32)
    x0, x1, y0, y1 = rect
    out[y0:y1 + 1, x0:x1 + 1] = idx_crop
    return out


def save_part(name, sub_idx):
    Image.fromarray(index_to_rgba(sub_idx)).save(os.path.join(PARTS, name))


def fill_rect(idx, rect, value=-1):
    x0, x1, y0, y1 = rect
    idx[y0:y1 + 1, x0:x1 + 1] = value


def blank_outside(idx, keep_mask):
    idx[~keep_mask] = -1


def _rect_mask(shape, rect):
    m = np.zeros(shape, bool)
    x0, x1, y0, y1 = rect
    m[y0:y1 + 1, x0:x1 + 1] = True
    return m


if __name__ == '__main__':
    native = load_native()
    rgba, idx = rasterize(native, N, H, GROUND)
    Image.fromarray(rgba).save(os.path.join(PARTS, '_sprite96.png'))

    # ---- report detected clusters to pin landmarks ----------------------------------
    def cls_mask(groups):
        return np.isin(idx, groups)

    print('teal clusters (balls/caps/bulb/boot lamps):')
    for c in clusters(cls_mask(TEAL), gap=2):
        print('   x %2d..%2d y %2d..%2d  n=%d' % c)
    print('terracotta clusters (grippers):')
    for c in clusters(cls_mask((16, 17, 18)), gap=2):
        print('   x %2d..%2d y %2d..%2d  n=%d' % c)
    print('lamp clusters (chest):')
    for c in clusters(cls_mask(LAMP), gap=1):
        print('   x %2d..%2d y %2d..%2d  n=%d' % c)
    print('green eye clusters:')
    for c in clusters(cls_mask(GREEN), gap=2):
        print('   x %2d..%2d y %2d..%2d  n=%d' % c)

    # ---- landmark rects (from dump_map/dump_seam run read-out) -----------------------
    R = {
        'antenna':   (40, 56, 2, 15),
        'head':      (14, 85, 16, 53),
        'eyeL':      (35, 45, 32, 44),
        'eyeR':      (56, 66, 32, 44),
        'shoulderL': (25, 33, 55, 62),
        'shoulderR': (62, 70, 55, 62),
        'segUpperL': (25, 30, 63, 65),
        'segUpperR': (64, 70, 63, 65),
        'segForeL':  (22, 32, 66, 72),
        'segForeR':  (63, 73, 66, 72),
        'segWristL': (22, 32, 73, 75),
        'segWristR': (63, 73, 73, 75),
        'segGripL':  (21, 31, 76, 81),
        'segGripR':  (64, 74, 76, 81),
    }
    chainL = (21, 32, 63, 81)
    chainR = (63, 74, 63, 81)

    # ---- moving chains and shoulder balls are cut out of the base -------------------
    base = idx.copy()
    fill_rect(base, (14, 85, 0, 53))          # head+antenna removed
    fill_rect(base, chainL)
    fill_rect(base, chainR)
    fill_rect(base, R['shoulderL'])
    fill_rect(base, R['shoulderR'])

    head = cut(idx, R['head'])
    # eyes cut out of head (movable parts) leaving faceplate (index 0)
    for key in ('eyeL', 'eyeR'):
        x0, x1, y0, y1 = R[key]
        sub = head[y0 - R['head'][2]:y1 - R['head'][2] + 1, x0 - R['head'][0]:x1 - R['head'][0] + 1]
        eye_mask = np.isin(sub, GREEN + WHITE)
        # also blank slightly beyond green/white: any non-dark faceplate pixel inside
        sub[eye_mask] = 0
    save_part('head.png', full(head, R['head']))
    save_part('base.png', base)
    save_part('antenna.png', full(cut(idx, R['antenna']), R['antenna']))

    for key, name in (('eyeL', 'eyeL.png'), ('eyeR', 'eyeR.png')):
        x0, x1, y0, y1 = R[key]
        eye = cut(idx, (x0, x1, y0, y1))
        eye[~np.isin(eye, GREEN + WHITE)] = -1
        save_part(name, full(eye, (x0, x1, y0, y1)))

    for key in ('shoulderL', 'shoulderR'):
        sub = cut(idx, R[key])
        sub[~np.isin(sub, TEAL + DARK)] = -1
        save_part(key + '.png', full(sub, R[key]))

    for key, name in (('segUpperL', 'seg_upperL.png'), ('segUpperR', 'seg_upperR.png'),
                      ('segForeL', 'seg_foreL.png'), ('segForeR', 'seg_foreR.png'),
                      ('segWristL', 'seg_wristL.png'), ('segWristR', 'seg_wristR.png'),
                      ('segGripL', 'seg_gripL.png'), ('segGripR', 'seg_gripR.png')):
        save_part(name, full(cut(idx, R[key]), R[key]))

    save_part('chainL.png', full(cut(idx, chainL), chainL))
    save_part('chainR.png', full(cut(idx, chainR), chainR))

    # ---- light masks (full-canvas 8-bit) ---------------------------------------------
    def save_mask(name, mask):
        Image.fromarray(mask.astype(np.uint8) * 255, 'L').save(os.path.join(PARTS, name))

    for key, name in (('eyeL', 'mask_eyeL.png'), ('eyeR', 'mask_eyeR.png')):
        x0, x1, y0, y1 = R[key]
        m = np.zeros((N, N), bool)
        m[y0:y1 + 1, x0:x1 + 1] = np.isin(cut(idx, (x0, x1, y0, y1)), GREEN)
        save_mask(name, m)
    m = np.zeros((N, N), bool)
    ax0, ax1, ay0, ay1 = R['antenna']
    m[ay0:ay1 + 1, ax0:ax1 + 1] = np.isin(cut(idx, R['antenna']), TEAL)
    save_mask('mask_antenna.png', m)
    chest_rect = (38, 58, 58, 63)
    save_mask('mask_chest.png', _rect_mask(idx.shape, chest_rect))
    # the three chest lamps as explicit rects (colour clusters are unreliable here:
    # the salmon lamp shares palette indices with the grippers)
    lamp_rects = [(44, 46, 60, 62), (49, 51, 60, 62), (53, 55, 60, 62)]
    for i, lr in enumerate(lamp_rects):
        sub = cut(idx, lr)
        m = np.zeros((N, N), bool)
        m[lr[2]:lr[3] + 1, lr[0]:lr[1] + 1] = ~np.isin(sub, (0, 1, 2, 9, 10, 11)) & (sub >= 0)
        save_mask('mask_lamp%d.png' % i, m)

    # ---- pivots ----------------------------------------------------------------------
    def centroid_of(rect, groups):
        x0, x1, y0, y1 = rect
        m = np.isin(idx[y0:y1 + 1, x0:x1 + 1], groups)
        ys, xs = np.nonzero(m)
        return (round(float(xs.mean()) + x0, 2), round(float(ys.mean()) + y0, 2))

    pivots = {
        'canvas': [N, N],
        'ground_y': GROUND,
        'char_height': H,
        'shoulderL': centroid_of(R['shoulderL'], TEAL),
        'shoulderR': centroid_of(R['shoulderR'], TEAL),
        'neck': [48.0, 55.0],
        'head_anchor': [48.0, 53.0],
        'chainL_rect': list(chainL),
        'chainR_rect': list(chainR),
        'segments': {k: list(v) for k, v in R.items()},
        'chest_rect': list(chest_rect),
        'chest_lamps': [list(r) for r in lamp_rects],
    }
    with open(os.path.join(HERE, 'parts.json'), 'w') as f:
        json.dump(pivots, f, indent=1)

    print('wrote parts.json (palette.json is maintained by hand in source/)')
    print('pivots:', json.dumps({k: pivots[k] for k in ('shoulderL', 'shoulderR', 'neck')}))
    print('chest lamps:', pivots['chest_lamps'])
