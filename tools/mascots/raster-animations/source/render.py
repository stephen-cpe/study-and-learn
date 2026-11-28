"""Renderer: composes frames from the editable parts and a per-frame state, and
encodes transparent GIFs with one fixed global palette.

Frame state (see timelines.py):
  head  (dx, dy)   head assembly offset at the neck (whole pixels)
  gaze  (dx, dy)   eye offset inside the faceplate (whole pixels)
  blink float      eye openness 1 = open, ~0.45 half, ~0.15 line, 0 closed
  eye   cue name   eye light cue (palette.json -> cues.eye)
  ant   cue name   antenna bulb cue (palette.json -> cues.antenna)
  lamps (c0,c1,c2) chest lamp cues (palette.json -> cues.lamp)
  armL  pose name  viewer's left arm chain pose ('r0'..'r7')
  armR  pose name  viewer's right arm chain pose (Raster's anatomical left)
  tapL  (dx, dy)   whole-pixel chain offset (small gripper taps)
  tapR  (dx, dy)

Layer order: base -> head group (head + antenna + eyes) -> shoulders -> chains.
Moving chains are never baked into the base, so the neutral hands disappear from
their original locations when a chain is drawn in a raised pose.

Usage:
  python render.py               # build every animation + manifest.json
  python render.py hello         # rebuild one clip (manifest.json is refreshed)
"""
from PIL import Image
import numpy as np
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
PARTS = os.path.join(HERE, 'parts')
POSE_ART = os.path.join(HERE, 'pose_art')

N, H, GROUND = 96, 90, 91

with open(os.path.join(HERE, 'palette.json')) as f:
    PALETTE_DOC = json.load(f)


def hex2rgb(h):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def build_unified():
    """fixed palette + every cue colour, in one stable order (GIF global palette)."""
    cols = [hex2rgb(h) for h in PALETTE_DOC['fixed_palette']]
    for group in PALETTE_DOC['cues'].values():
        for ramp in group.values():
            if ramp:
                for h in ramp:
                    c = hex2rgb(h)
                    if c not in cols:
                        cols.append(c)
    return cols


UNIFIED = build_unified()
UIX = {c: i for i, c in enumerate(UNIFIED)}
LUM = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in UNIFIED]
ART_UIX = list(range(len(PALETTE_DOC['fixed_palette'])))   # first 31 = art palette


def cue_ramp(kind, name):
    """Unified indices for a cue ramp (light -> dark), or None for 'base'."""
    if name == 'base':
        return None
    ramp = PALETTE_DOC['cues'][kind][name]
    return [UIX[hex2rgb(h)] for h in ramp]


class Rig:
    def __init__(self):
        self.layer = {}
        for name in ('base', 'head', 'antenna', 'eyeL', 'eyeR',
                     'shoulderL', 'shoulderR'):
            self.layer[name] = self._load_png(os.path.join(PARTS, name + '.png'))
        self.masks = {}
        for name in ('mask_eyeL', 'mask_eyeR', 'mask_antenna',
                     'mask_lamp0', 'mask_lamp1', 'mask_lamp2'):
            m = np.array(Image.open(os.path.join(PARTS, name + '.png')).convert('L'))
            self.masks[name] = m > 127
        self.poses = {}
        for side in ('L', 'R'):
            for pname in ('r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7'):
                key = '%s_%s' % (side, pname)
                self.poses[key] = self._load_png(os.path.join(POSE_ART, key + '.png'))
        with open(os.path.join(HERE, 'parts.json')) as f:
            self.geom = json.load(f)

    @staticmethod
    def _load_png(path):
        a = np.array(Image.open(path).convert('RGBA'))
        idx = np.full(a.shape[:2], -1, np.int32)
        ok = a[..., 3] > 0
        if ok.any():
            flat = a[..., :3][ok].astype(int)
            pal = np.array(UNIFIED, int)
            d = ((flat[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
            idx[ok] = d.argmin(axis=1)
        return idx

    # -- helpers ---------------------------------------------------------------------
    @staticmethod
    def _paste(dst, src, dx=0, dy=0):
        for y in range(src.shape[0]):
            ty = y + dy
            if not (0 <= ty < dst.shape[0]):
                continue
            row = src[y]
            xs = np.nonzero(row >= 0)[0]
            for x in xs:
                tx = x + dx
                if 0 <= tx < dst.shape[1]:
                    dst[ty, tx] = row[x]

    @staticmethod
    def _recolor(idx, mask, ramp):
        if ramp is None:
            return idx
        out = idx.copy()
        vals = idx[mask & (idx >= 0)]
        if vals.size == 0:
            return out
        present = sorted(set(vals.tolist()), key=lambda c: -LUM[c])
        k = len(ramp)
        for i, c in enumerate(present):
            out[(idx == c) & mask] = ramp[min(i * k // len(present), k - 1)]
        return out

    # -- frame composition -----------------------------------------------------------
    def frame(self, st):
        idx = self.layer['base'].copy()

        # head group (head shell + antenna + eyes) travels together at the neck
        hx, hy = st['head']
        gx, gy = st['gaze']
        head = self.layer['head'].copy()
        antenna = self._recolor(self.layer['antenna'].copy(),
                                self.masks['mask_antenna'], cue_ramp('antenna', st['ant']))
        eyeL = self._recolor(self.layer['eyeL'].copy(),
                             self.masks['mask_eyeL'], cue_ramp('eye', st['eye']))
        eyeR = self._recolor(self.layer['eyeR'].copy(),
                             self.masks['mask_eyeR'], cue_ramp('eye', st['eye']))
        openness = st.get('blink', 1.0)
        if openness < 0.999:
            for eye in (eyeL, eyeR):
                rows = np.nonzero((eye >= 0).any(axis=1))[0]
                if rows.size == 0:
                    continue
                cy = (rows.min() + rows.max()) / 2.0
                keep = max(0, int(round((rows.max() - rows.min() + 1) * openness)))
                if keep == 0:
                    eye[:] = -1
                else:
                    y0 = int(round(cy - (keep - 1) / 2.0))
                    for y in range(eye.shape[0]):
                        if not (y0 <= y < y0 + keep):
                            eye[y, :] = -1
        group = head
        self._paste(group, antenna, hx, hy)
        self._paste(group, eyeL, hx + gx, hy + gy)
        self._paste(group, eyeR, hx + gx, hy + gy)
        self._paste(idx, group, hx, hy)

        # chest lamps (mask on the base layer, before arms move over it)
        for i in range(3):
            ramp = cue_ramp('lamp', st['lamps'][i])
            if ramp is not None:
                idx = self._recolor(idx, self.masks['mask_lamp%d' % i], ramp)

        # shoulder balls stay on the pivots; chains swing about them
        self._paste(idx, self.layer['shoulderL'])
        self._paste(idx, self.layer['shoulderR'])
        self._paste(idx, self.poses['L_' + st['armL']], st['tapL'][0], st['tapL'][1])
        self._paste(idx, self.poses['R_' + st['armR']], st['tapR'][0], st['tapR'][1])
        return idx


def idx_to_p_image(idx, transparent):
    """Map an index grid to a PIL 'P' image against the fixed unified palette."""
    out = np.full(idx.shape, transparent, np.uint8)
    ok = idx >= 0
    out[ok] = idx[ok].astype(np.uint8)
    img = Image.fromarray(out, 'P')
    pal = []
    for c in UNIFIED:
        pal.extend(c)
    pal.extend([0, 0, 0] * (256 - len(UNIFIED)))
    img.putpalette(pal)
    return img


def idx_to_rgba(idx):
    a = np.zeros(idx.shape + (4,), np.uint8)
    ok = idx >= 0
    if ok.any():
        a[ok, :3] = np.array(UNIFIED, np.uint8)[idx[ok]]
        a[ok, 3] = 255
    return Image.fromarray(a, 'RGBA')


def build_clip(rig, name, clip):
    from timelines import pose_label
    frames_dir = os.path.join(OUT, 'frames', name)
    gifs_dir = os.path.join(OUT, 'gifs')
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(gifs_dir, exist_ok=True)
    for old in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, old))

    states = clip['frames']
    p_frames = []
    png_names = []
    durations = []
    for i, (st, ms) in enumerate(states):
        idx = rig.frame(st)
        rgba = idx_to_rgba(idx)
        fname = '%03d.png' % i
        rgba.save(os.path.join(frames_dir, fname))
        png_names.append('frames/%s/%s' % (name, fname))
        # GIF delays are stored with 10 ms resolution (centiseconds) - snap exactly
        # the way the encoder quantises, so manifest and file always agree
        durations.append(max(10, int(ms / 10.0) * 10))
        p_frames.append(idx_to_p_image(idx, len(UNIFIED)))

    gif_path = os.path.join(gifs_dir, name + '.gif')
    kw = dict(save_all=True, append_images=p_frames[1:], duration=durations,
              transparency=len(UNIFIED), disposal=2)
    if clip['mode'] == 'loop':
        kw['loop'] = 0
    p_frames[0].save(gif_path, **kw)

    entry = {
        'name': name,
        'filename': 'gifs/%s.gif' % name,
        'mode': 'loop' if clip['mode'] == 'loop' else 'once',
        'frames': png_names,
        'frame_count': len(states),
        'durations_ms': durations,
        'total_ms': int(sum(durations)),
        'start_pose': pose_label(states[0][0]),
        'end_pose': pose_label(states[-1][0]),
    }
    return entry


def manifest(rig, entries):
    return {
        'pack': 'raster-animations',
        'character': 'Raster (Azthreus Systems)',
        'canvas': {'width': N, 'height': N, 'ground_y': GROUND,
                   'char_height_px': H,
                   'note': '96x96 working grid (see README: 72x72 lost the wrist and '
                           'closed the gripper notch on this artwork)'},
        'arms': {'armL': "viewer's left arm = Raster's anatomical right (static in hello)",
                 'armR': "viewer's right arm = Raster's anatomical left (the waving arm)"},
        'palette_file': 'source/palette.json',
        'animations': entries,
    }


def main():
    from timelines import CLIPS
    want = [a for a in sys.argv[1:] if not a.startswith('-')]
    names = want if want else list(CLIPS.keys())
    rig = Rig()
    entries = []
    existing = {}
    mpath = os.path.join(OUT, 'manifest.json')
    if os.path.exists(mpath) and want:
        with open(mpath) as f:
            existing = {e['name']: e for e in json.load(f)['animations']}
    for name in names:
        if name not in CLIPS:
            print('unknown clip:', name)
            continue
        e = build_clip(rig, name, CLIPS[name])
        existing[name] = e
        print('built %-22s %2d frames %5d ms  %s' %
              (name, e['frame_count'], e['total_ms'], e['mode']))
    if want:
        entries = [existing[k] for k in CLIPS.keys() if k in existing]
    else:
        entries = [existing[k] for k in names]
    with open(mpath, 'w') as f:
        json.dump(manifest(rig, entries), f, indent=1)
    print('wrote manifest.json (%d animations)' % len(entries))


if __name__ == '__main__':
    main()
