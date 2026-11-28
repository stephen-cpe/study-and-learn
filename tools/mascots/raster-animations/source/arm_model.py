"""Raster arm model: rigid chain (upper + forearm + wrist + gripper) rotating about
the teal shoulder-ball pivot.

Each pose is generated from the arm chain's own pixel data extracted from raster.png:
  * geometry   - inverse-mapped nearest rotation about the pivot, whole-pixel output
                 (no gaps or holes at diagonal angles)
  * shading    - each segment keeps its own colour multiset, reassigned along the
                 screen up-left -> down-right axis ("upper-left highlights" at every
                 angle and on both arms)
  * structure  - the gripper notch is force-reopened at the tip and the dark wrist
                 band is force-kept, so neither can collapse in diagonal poses

Poses export as editable PNGs (source/poses/). Hand corrections can be layered in via
source/poses_corrections.json ("edits": [{"pose": "R_r5", "set": [[x,y,"#hex"],...],
"clear": [[x,y],...] }]) without touching this code.
"""
from PIL import Image
import numpy as np
import json
import math
import os

from rasterize import PALETTE

HERE = os.path.dirname(os.path.abspath(__file__))
POSE_DIR = os.path.join(HERE, 'poses')

N, H, GROUND = 96, 90, 91

SEGMENTS = ('upper', 'fore', 'wrist', 'grip')

OUTLINE = {0, 1, 10, 11}
SEG_SHADE = {
    'upper': {2, 9},
    'fore': {12, 13, 14, 15, 27},
    'wrist': {2, 9, 11},
    'grip': {16, 17, 18, 30},
}
WRIST_DARK = {2, 9, 10, 11}
LUM = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in PALETTE]

# pose ladder: swing out of vertical, degrees, toward each arm's outward side
POSES = [('r0', 0), ('r1', 22), ('r2', 45), ('r3', 68), ('r4', 90),
         ('r5', 110), ('r6', 121), ('r7', 133)]

# gripper notch slot measured from the extracted art (pivot-local t of the gap centre,
# s where the notch ceiling starts).  Editable here; rebuilt poses pick it up.
NOTCH = {'L': {'t_center': -1.9, 't_half': 1.2, 's_start': 19.5},
         'R': {'t_center': 2.0, 't_half': 1.2, 's_start': 19.5}}


class Chain:
    """One arm chain template in pivot-local coordinates.

    Rest frame (theta=0, arm hangs down): +s down the arm, +t to screen right.
    """

    def __init__(self, name, idx_full, rect, pivot, seg_rects):
        self.name = name
        self.rect = rect
        self.pivot = pivot
        self.side = -1 if name == 'L' else 1
        self.notch = NOTCH[name]
        self.pixel_map = {}          # canvas (x, y) -> (color, segment)
        self.tip_s = 0.0
        for seg in SEGMENTS:
            sx0, sx1, sy0, sy1 = seg_rects[seg]
            for y in range(sy0, sy1 + 1):
                for x in range(sx0, sx1 + 1):
                    v = int(idx_full[y, x])
                    if v < 0:
                        continue
                    self.pixel_map[(x, y)] = (v, seg)
                    self.tip_s = max(self.tip_s, y - pivot[1])

    # -- geometry ---------------------------------------------------------------
    def place(self, theta_deg, ss=2):
        """Inverse-map: target (X, Y) canvas pixels -> (color, segment, local_s).

        theta is the swing out of vertical toward this arm's outward side.
        Sub-pixel supersampling (ss x ss samples per pixel) keeps silhouettes solid
        at diagonal angles instead of leaving aliasing dust and holes.
        """
        th = math.radians(theta_deg)
        c, s = math.cos(th), math.sin(th)
        k = self.side
        px, py = self.pivot
        votes = {}       # (X, Y) -> Counter of (color, segment)
        reach = int(self.tip_s) + 6
        offs = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)][:ss * ss]
        if ss == 3:
            offs = [(a / 3.0, b / 3.0) for a in (-1, 0, 1) for b in (-1, 0, 1)]
        for Y in range(int(py) - reach, int(py) + reach + 1):
            for X in range(int(px) - reach, int(px) + reach + 1):
                hits = []
                for (ox, oy) in offs:
                    dx, dy = X + ox - px, Y + oy - py
                    lx = c * dx - k * s * dy
                    ly = k * s * dx + c * dy
                    sx = int(round(px + lx))
                    sy = int(round(py + ly))
                    hit = self.pixel_map.get((sx, sy))
                    if hit is not None:
                        hits.append((hit[0], hit[1], ly))
                if len(hits) >= (len(offs) + 1) // 2:
                    # majority colour among the hits (ly is averaged per colour)
                    agg = {}
                    for (hc, hs, hl) in hits:
                        e = agg.setdefault((hc, hs), [0, 0.0])
                        e[0] += 1
                        e[1] += hl
                    (hc, hs), (n, ssum) = max(agg.items(), key=lambda kv: kv[1][0])
                    votes[(X, Y)] = (hc, hs, ssum / n)
        # silhouette cleanup: drop isolated dust, fill one-pixel holes
        filled = set(votes)
        drop = []
        for (X, Y) in filled:
            n = sum(1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    if (dx or dy) and (X + dx, Y + dy) in filled)
            if n <= 1:
                drop.append((X, Y))
        for p in drop:
            votes.pop(p, None)
        filled = set(votes)
        add = {}
        for (X, Y) in list(filled):
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (X + dx, Y + dy)
                    if q in filled:
                        continue
                    n = sum(1 for ax in (-1, 0, 1) for ay in (-1, 0, 1)
                            if (ax or ay) and (q[0] + ax, q[1] + ay) in filled)
                    if n >= 7:
                        add[q] = votes[(X, Y)]
        votes.update(add)
        placed = {}
        for (X, Y), (col, seg, ls) in votes.items():
            placed[(X, Y)] = (col, seg, ls)
        return placed

    def render_pose(self, theta_deg):
        """Full-canvas index grid for the posed chain (-1 = transparent)."""
        idx = np.full((N, N), -1, np.int32)
        placed = self.place(theta_deg)

        slots = {seg: [] for seg in SEGMENTS}
        for (X, Y), (col, seg, ls) in placed.items():
            if col in OUTLINE or col not in SEG_SHADE[seg]:
                idx[Y, X] = col            # outlines / structure keep their colour
            else:
                slots[seg].append((X, Y, col, ls))

        # shading: per segment, reassign its own colour multiset along the
        # screen up-left -> down-right axis (light source stays upper-left)
        for seg in SEGMENTS:
            items = slots[seg]
            if not items:
                continue
            order = sorted(items, key=lambda it: (it[0] + it[1], it[2]))
            cols = sorted((it[2] for it in items), key=lambda c: -LUM[c])
            for i, (X, Y, _c, _s) in enumerate(order):
                idx[Y, X] = cols[i % len(cols)] if len(cols) < len(order) else cols[i]

        # force the gripper notch slot open at the tip
        nt = self.notch
        for (X, Y), (col, seg, ls) in placed.items():
            if seg != 'grip' or ls < nt['s_start']:
                continue
            lx, ly = self._local(X, Y, theta_deg)
            if abs(lt_center(lx, nt)) <= nt['t_half']:
                idx[Y, X] = -1

        # force the wrist band dark and unbroken
        for (X, Y), (col, seg, ls) in placed.items():
            if seg == 'wrist' and idx[Y, X] not in OUTLINE and idx[Y, X] not in WRIST_DARK:
                idx[Y, X] = 9
        return idx

    def _local(self, X, Y, theta_deg):
        th = math.radians(theta_deg)
        c, s = math.cos(th), math.sin(th)
        k = self.side
        dx, dy = X - self.pivot[0], Y - self.pivot[1]
        return (c * dx - k * s * dy, k * s * dx + c * dy)


def lt_center(lx, nt):
    return lx - nt['t_center']


def load_chain(side):
    """Build the chain template from the exported parts."""
    with open(os.path.join(HERE, 'parts.json')) as f:
        pj = json.load(f)
    rect = tuple(pj['chain%s_rect' % side])
    pivot = tuple(pj['shoulder%s' % side])
    seg_rects = {
        'upper': tuple(pj['segments']['segUpper%s' % side]),
        'fore': tuple(pj['segments']['segFore%s' % side]),
        'wrist': tuple(pj['segments']['segWrist%s' % side]),
        'grip': tuple(pj['segments']['segGrip%s' % side]),
    }
    img = Image.open(os.path.join(HERE, 'parts', 'chain%s.png' % side)).convert('RGBA')
    a = np.array(img)
    idx = np.full(a.shape[:2], -1, np.int32)
    ok = a[..., 3] > 0
    flat = a[..., :3][ok].astype(int)
    pal = np.array(PALETTE, int)
    d = ((flat[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
    idx[ok] = d.argmin(axis=1)
    return Chain(side, idx, rect, pivot, seg_rects)

def apply_corrections(idx, pose_key):
    """Layer hand corrections from poses_corrections.json onto a rendered pose."""
    path = os.path.join(HERE, 'poses_corrections.json')
    if not os.path.exists(path):
        return idx
    with open(path) as f:
        doc = json.load(f)
    hexmap = {'#%02x%02x%02x' % c: i for i, c in enumerate(PALETTE)}
    for ed in doc.get('edits', []):
        if ed.get('pose') not in (pose_key, '*'):
            continue
        for x, y in ed.get('clear', []):
            idx[y, x] = -1
        for x, y, hexcol in ed.get('set', []):
            idx[y, x] = hexmap[hexcol.lower()]
    return idx
