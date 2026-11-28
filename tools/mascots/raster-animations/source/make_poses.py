"""Generate the hand pose silhouettes for both arms and QA them.

Run after make_parts.py.  Outputs editable pose PNGs into source/poses/ and a
contact sheet for visual inspection.  Hand edits belong in poses_corrections.json;
re-run this file (or render.py, which regenerates poses) to rebuild.

QA printed per pose (also re-checked by verify.py on the exported frames):
  wrist   dark band pixels kept in the wrist segment (must stay attached + visible)
  notch   open gap between the two gripper jaws at the tip (must stay open)
  grip    terracotta pixel count (the gripper must stay identifiable at any angle)
  torso   grip pixels intersecting the torso box (must be 0 at the raised poses:
          "at the top, the hand must visibly clear the torso")
"""
from PIL import Image, ImageDraw
import numpy as np
import json
import os

from rasterize import PALETTE, index_to_rgba
from arm_model import Chain, load_chain, apply_corrections, POSES, WRIST_DARK, N

HERE = os.path.dirname(os.path.abspath(__file__))
POSE_DIR = os.path.join(HERE, 'pose_art')
os.makedirs(POSE_DIR, exist_ok=True)

TERRA = {16, 17, 18, 30}
TORSO_BOX = (33, 62, 54, 91)     # x0, x1, y0, y1: torso + hips (no arms)


def qa(chain, idx, theta, tag):
    placed = chain.place(theta)
    nt = chain.notch
    wrist_n = grip_n = slot_filled = jaw_l = jaw_r = 0
    for (X, Y), (col, seg, ls) in placed.items():
        if idx[Y, X] < 0:
            continue
        if seg == 'wrist' and idx[Y, X] in WRIST_DARK:
            wrist_n += 1
        if seg == 'grip':
            if idx[Y, X] in TERRA:
                grip_n += 1
            if ls >= nt['s_start'] + 1.0:
                d = chain._local(X, Y, theta)[0] - nt['t_center']
                if abs(d) <= nt['t_half']:
                    slot_filled += 1
                elif -4.5 <= d < -nt['t_half']:
                    jaw_l += 1
                elif nt['t_half'] < d <= 4.5:
                    jaw_r += 1
    x0, x1, y0, y1 = TORSO_BOX
    in_torso = int((idx[y0:y1 + 1, x0:x1 + 1] >= 0).sum())
    ok = (slot_filled == 0 and jaw_l >= 2 and jaw_r >= 2 and wrist_n >= 5
          and grip_n >= 12)
    print('  %-8s wrist %2d px | notch slot %d filled (0=clear) jaws %d/%d | grip %2d px | '
          'overlap torso %d  %s'
          % (tag, wrist_n, slot_filled, jaw_l, jaw_r, grip_n, in_torso,
             'OK' if ok else 'CHECK'))
    return ok


if __name__ == '__main__':
    chains = {s: load_chain(s) for s in ('L', 'R')}
    sheet_cells = []
    all_ok = True
    for side in ('R', 'L'):
        ch = chains[side]
        for name, theta in POSES:
            key = '%s_%s' % (side, name)
            idx = ch.render_pose(theta)
            idx = apply_corrections(idx, key)
            img = Image.fromarray(index_to_rgba(idx))
            img.save(os.path.join(POSE_DIR, key + '.png'))
            print('%s (theta=%d):' % (key, theta))
            all_ok &= qa(ch, idx, theta, key)
            sheet_cells.append((key + ' %d deg' % theta, idx))
    print('ALL POSES OK' if all_ok else 'SOME POSES NEED WORK')

    # contact sheet at 5x on light and dark halves
    S = 5
    cell = N * S + 8
    cols = 4
    rows = (len(sheet_cells) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * cell), (235, 235, 238))
    dr = ImageDraw.Draw(sheet)
    for i, (label, idx) in enumerate(sheet_cells):
        img = Image.fromarray(index_to_rgba(idx)).resize((N * S, N * S), Image.NEAREST)
        cx = (i % cols) * cell + 4
        cy = (i // cols) * cell + 4
        bg = Image.new('RGBA', (N * S, N * S), (235, 235, 238, 255))
        bg.alpha_composite(img)
        sheet.paste(bg.convert('RGB'), (cx, cy))
        dr.text((cx + 4, cy + 4), label, fill=(200, 0, 0))
    sheet.save(os.path.join(HERE, '_pose_sheet.png'))
    print('saved _pose_sheet.png')
