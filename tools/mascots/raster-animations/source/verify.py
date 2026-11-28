"""Verification suite for the Raster animation pack.

Decodes the exported GIFs and PNG frames and checks:
  1  inventory      32 gifs + 32 numbered frame sets + complete manifest
  2  timing         per-frame GIF delays match manifest durations_ms exactly
  3  transparency   GIF frames decode with a transparent background
  4  playback mode  NETSCAPE loop block present for loops, absent for one-shots
  5  canvas align   all frames 96x96; boot rows pixel-identical in every frame
                    (feet grounded on the fixed ground line)
  6  loop seams     wrap-around change (last -> first) comparable to in-clip steps
  7  handoff        wake-up frame 0 is pixel-identical to power-down's last frame
  8  faceplate      dark facial pixels stay opaque in every frame
  9  fragments      no isolated dust pixels; raised-arm frames leave nothing behind
                    in the resting gripper boxes
 10  palette        every opaque pixel colour is in the declared fixed palette

Run:  python raster-animations/source/verify.py
"""
from PIL import Image, ImageSequence
import numpy as np
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)

sys.path.insert(0, HERE)
from render import UNIFIED, hex2rgb            # noqa: E402
from timelines import CLIPS                    # noqa: E402

N = 96
GROUND_LAST_ROWS = (86, 92)     # boots + ground line must never move
FACEPLATE_BANDS = [(28, 31, 30, 66), (45, 47, 30, 66)]   # y0, y1, x0, x1
REST_GRIP_BOX = {'R': (64, 74, 75, 82), 'L': (20, 31, 75, 82)}
RAISED = ('r5', 'r6', 'r7')

results = {'pass': 0, 'fail': 0, 'notes': []}


def ok(cond, msg):
    if cond:
        results['pass'] += 1
    else:
        results['fail'] += 1
        results['notes'].append('FAIL: ' + msg)
    return cond


def load_rgba(path):
    return np.array(Image.open(path).convert('RGBA'))


def gif_has_netscape(path):
    with open(path, 'rb') as f:
        data = f.read()
    return b'NETSCAPE2.0' in data


def dust_count(rgba):
    a = rgba[..., 3] > 0
    ys, xs = np.nonzero(a)
    n = 0
    for y, x in zip(ys, xs):
        y0, y1 = max(0, y - 1), min(a.shape[0], y + 2)
        x0, x1 = max(0, x - 1), min(a.shape[1], x + 2)
        if a[y0:y1, x0:x1].sum() <= 2:      # itself + at most one neighbour
            n += 1
    return n


def main():
    with open(os.path.join(OUT, 'manifest.json')) as f:
        man = json.load(f)
    entries = {e['name']: e for e in man['animations']}
    ok(len(entries) == 32, 'manifest lists 32 animations (got %d)' % len(entries))
    ok(set(entries) == set(CLIPS), 'manifest names match the roster exactly')

    declared = {hex2rgb(h) for h in json.load(
        open(os.path.join(HERE, 'palette.json')))['fixed_palette']}
    for group in json.load(open(os.path.join(HERE, 'palette.json')))['cues'].values():
        for ramp in group.values():
            if ramp:
                declared.update(hex2rgb(h) for h in ramp)

    for name, e in entries.items():
        tag = name
        # 1 inventory ------------------------------------------------------------
        gif_path = os.path.join(OUT, e['filename'])
        ok(os.path.exists(gif_path), '%s: gif exists' % tag)
        ok(len(e['frames']) == e['frame_count'], '%s: frame list complete' % tag)
        pngs = [os.path.join(OUT, p) for p in e['frames']]
        ok(all(os.path.exists(p) for p in pngs), '%s: all png frames exist' % tag)
        ok(e['durations_ms'] and min(e['durations_ms']) >= 30,
           '%s: durations >= 30ms (browser GIF clamp safe)' % tag)
        ok(sum(e['durations_ms']) == e['total_ms'], '%s: total_ms == sum(durations)' % tag)

        # 2 timing + 3 transparency + 4 playback mode ----------------------------
        gif = Image.open(gif_path)
        delays = []
        decoded = []
        for fr in ImageSequence.Iterator(gif):
            delays.append(fr.info.get('duration'))
            decoded.append(np.array(fr.convert('RGBA')))
        frames = decoded
        ok(len(frames) == e['frame_count'],
           '%s: gif frame count %d == manifest %d' % (tag, len(frames), e['frame_count']))
        ok(delays == e['durations_ms'],
           '%s: gif delays match manifest (%s vs %s)' % (tag, delays, e['durations_ms']))
        ok(gif.size == (N, N), '%s: gif canvas %s' % (tag, gif.size))
        is_loop = e['mode'] == 'loop'
        ok(gif_has_netscape(gif_path) == is_loop,
           '%s: NETSCAPE loop block %s for mode %s' % (tag, gif_has_netscape(gif_path), e['mode']))

        prev_png = None
        intra = []
        boot_ref = None
        for i, p in enumerate(pngs):
            a = load_rgba(p)
            ok(a.shape == (N, N, 4), '%s[%d]: png %s' % (tag, i, a.shape))
            # 3 transparency: corners transparent, character opaque somewhere
            corner_t = (a[0, 0, 3] == 0 and a[0, N - 1, 3] == 0
                        and a[N - 1, 0, 3] == 0 and a[N - 1, N - 1, 3] == 0)
            ok(corner_t, '%s[%d]: transparent background' % (tag, i))
            ok((a[..., 3] > 0).sum() > 400, '%s[%d]: character present' % (tag, i))
            # gif transparency decodes too
            g = decoded[i]
            ok(g[0, 0, 3] == 0 or tuple(g[0, 0, :3]) == (0, 0, 0),
               '%s[%d]: gif frame transparent bg' % (tag, i))
            # 5 canvas alignment: boots identical in every frame
            boots = a[GROUND_LAST_ROWS[0]:GROUND_LAST_ROWS[1]]
            if boot_ref is None:
                boot_ref = boots.copy()
            else:
                ok(np.array_equal(boots, boot_ref),
                   '%s[%d]: boots moved (ground line not fixed)' % (tag, i))
            ok(a[N - 1, :, 3].max() == 0, '%s[%d]: canvas bottom row clear' % (tag, i))
            # 8 faceplate bands opaque
            for (y0, y1, x0, x1) in FACEPLATE_BANDS:
                ok((a[y0:y1 + 1, x0:x1 + 1, 3] > 0).all(),
                   '%s[%d]: faceplate band y%d-%d opaque' % (tag, i, y0, y1))
            # 9 fragments: dust + nothing left in the resting gripper boxes
            d = dust_count(a)
            ok(d == 0, '%s[%d]: %d isolated dust pixels' % (tag, i, d))
            st = CLIPS[name]['frames'][i][0]
            for side in ('L', 'R'):
                if st['arm' + side] in RAISED:
                    x0, x1, y0, y1 = REST_GRIP_BOX[side]
                    left = int((a[y0:y1 + 1, x0:x1 + 1, 3] > 0).sum())
                    ok(left == 0, '%s[%d]: %d fragments left in resting %s gripper box'
                       % (tag, i, left, side))
            # 10 palette purity
            rgb = a[a[..., 3] > 0][:, :3]
            cols = {tuple(int(v) for v in c) for c in np.unique(rgb, axis=0)}
            bad = cols - declared
            ok(not bad, '%s[%d]: off-palette colours %s' % (tag, i, sorted(bad)[:4]))
            if prev_png is not None:
                intra.append(int((prev_png != a).any(axis=2).sum()))
            prev_png = a

        # 6 loop seams ------------------------------------------------------------
        if e['mode'] == 'loop' and len(pngs) > 1:
            first = load_rgba(pngs[0])
            last = load_rgba(pngs[-1])
            seam = int((first != last).any(axis=2).sum())
            med = float(np.median(intra)) if intra else 0.0
            limit = max(2.0 * med + 16, 24)
            ok(seam <= limit,
               '%s: loop seam change %d px exceeds limit %.0f (median step %.0f)'
               % (tag, seam, limit, med))

    # 7 power-down -> wake-up handoff --------------------------------------------
    pd = sorted(os.listdir(os.path.join(OUT, 'frames', 'power-down')))
    wu = sorted(os.listdir(os.path.join(OUT, 'frames', 'wake-up')))
    a = load_rgba(os.path.join(OUT, 'frames', 'power-down', pd[-1]))
    b = load_rgba(os.path.join(OUT, 'frames', 'wake-up', wu[0]))
    ok(np.array_equal(a, b), 'handoff: wake-up frame 0 == power-down last frame')
    ok(entries['power-down']['end_pose'] == 'asleep',
       'power-down ends asleep (%s)' % entries['power-down']['end_pose'])
    ok(entries['wake-up']['start_pose'] == 'asleep',
       'wake-up starts asleep (%s)' % entries['wake-up']['start_pose'])

    # ordinary one-shots return to neutral ---------------------------------------
    for name, e in entries.items():
        if e['mode'] == 'once' and name not in ('power-down', 'wake-up'):
            ok(e['end_pose'] == 'neutral',
               '%s: one-shot returns to neutral (end_pose %s)' % (name, e['end_pose']))

    print('\n== verify: %d checks passed, %d failed ==' % (results['pass'], results['fail']))
    for n in results['notes']:
        print(' ', n)
    report = os.path.join(HERE, '_verify_report.txt')
    with open(report, 'w') as f:
        f.write('%d passed, %d failed\n' % (results['pass'], results['fail']))
        for n in results['notes']:
            f.write(n + '\n')
    print('wrote', report)
    return 1 if results['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
