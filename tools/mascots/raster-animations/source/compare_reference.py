"""Reference-versus-Raster hello comparison at equal displayed height.

Aligns the sample robot and Raster at the waving shoulder and scales them to the
same character height, then lays out rest / mid-lift / peak columns so the reach and
arc can be compared directly.  Also renders the 48 px and 96 px inspection views of
a chosen frame on light and dark stages.

Outputs (into source/):
  _hello_compare.png    sample (top) vs Raster (bottom), shoulder-aligned
  _hello_sizes.png      chosen frame at 48 px and 96 px on light/dark stages
"""
from PIL import Image, ImageDraw
import numpy as np
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WAVE = os.path.join(ROOT, 'references', 'mascots', 'wave')
OUT = os.path.join(ROOT, 'raster-animations')

# measured reference geometry (pixels of mascot-wave-frame0.png, 759x759)
REF = {'size': 759, 'char_box': (151, 70, 612, 663), 'shoulder': (507.0, 473.0)}
# measured Raster geometry (96x96 working grid)
RAST = {'size': 96, 'char_box': (14, 2, 84, 91), 'shoulder': (66.5, 58.5)}

CHAR_H = 360        # common displayed character height for the comparison


def _load(p):
    return Image.open(p).convert('RGBA')


def scaled_panel(img, char_box, shoulder, char_h, bg):
    """Scale a sprite so its character box is char_h tall; paste shoulder-aligned
    into a cell with the shoulder point at (0.68, 0.63) of the cell (the waving
    shoulder sits at ~76% of character width and ~62% down on both characters)."""
    x0, y0, x1, y1 = char_box
    s = char_h / (y1 - y0 + 1)
    w = int(round(img.width * s))
    h = int(round(img.height * s))
    im = img.resize((w, h), Image.NEAREST)
    sh = (shoulder[0] * s, shoulder[1] * s)
    cell_w = int(char_h * 0.95)
    cell_h = int(char_h * 1.12)
    cx, cy = int(cell_w * 0.68), int(cell_h * 0.63)
    canvas = Image.new('RGBA', (cell_w, cell_h), bg + (255,))
    canvas.alpha_composite(im, (int(cx - sh[0]), int(cy - sh[1])))
    return canvas, (cx, cy)


def hand_marker(img_path, kind, char_box, shoulder, char_h, cell, box=None):
    """Draw a small ring on the waving hand.

    kind 'raster'     - terracotta centroid below the chest
    kind 'sample'     - centroid of the farthest-changed cluster from the shoulder
    kind 'sample_box' - centroid of opaque pixels inside `box` (rest frame, no diff)
    """
    im = _load(img_path)
    a = np.array(im).astype(int)
    if kind == 'raster':
        r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
        m = (r > 150) & (g > 80) & (g < 210) & (b < 190) & (b < r - 30) & (al > 0)
        m[:58, :] = False                       # exclude the salmon chest lamp
        m[:, :58] = False                       # waving arm is the viewer's right one
    elif kind == 'sample_box':
        m = np.zeros(a.shape[:2], bool)
        bx0, by0, bx1, by1 = box
        m[by0:by1, bx0:bx1] = a[by0:by1, bx0:bx1, 3] > 0
    else:
        base = np.array(_load(os.path.join(WAVE, 'mascot-wave-frame0.png'))).astype(int)
        sx, sy = REF['shoulder']
        m = (a[..., 3] > 0) & (np.abs(a[..., :3] - base[..., :3]).sum(axis=2) > 60)
        m[:, :int(sx) - 30] = False             # waving side only
        m[:int(sy) - 200, :] = False            # drop the antenna / head bob
        m[int(sy) + 120:, :] = False
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return cell
    sx, sy = (REF if kind.startswith('sample') else RAST)['shoulder']
    d = np.hypot(xs - sx, ys - sy)
    far = d >= 0.75 * d.max()
    hx, hy = xs[far].mean(), ys[far].mean()
    x0, y0, x1, y1 = char_box
    s = char_h / (y1 - y0 + 1)
    reach = float(np.hypot(hx - sx, hy - sy)) / (char_box[3] - char_box[1] + 1)
    print('   %-22s hand at (%3.0f, %3.0f)  reach = %.3f of character height'
          % (os.path.basename(img_path), hx, hy, reach))
    hx, hy = hx * s, hy * s
    sh = (sx * s, sy * s)
    cx, cy = int(cell.width * 0.68), int(cell.height * 0.63)
    px, py = cx - sh[0] + hx, cy - sh[1] + hy
    dr = ImageDraw.Draw(cell)
    dr.ellipse((px - 7, py - 7, px + 7, py + 7), outline=(20, 90, 220, 255), width=2)
    return cell


def compare(columns, out_path):
    """columns = [(label, ref_frame_path, raster_frame_path), ...]"""
    bg = (233, 233, 238)
    cells = []
    for label, ref_p, rast_p, ref_kind, ref_box in columns:
        top, mk1 = scaled_panel(_load(ref_p), REF['char_box'], REF['shoulder'], CHAR_H, bg)
        bot, mk2 = scaled_panel(_load(rast_p), RAST['char_box'], RAST['shoulder'], CHAR_H, bg)
        top = hand_marker(ref_p, ref_kind, REF['char_box'], REF['shoulder'], CHAR_H, top,
                          box=ref_box)
        bot = hand_marker(rast_p, 'raster', RAST['char_box'], RAST['shoulder'], CHAR_H, bot)
        cells.append((label, top, mk1, bot, mk2))
    cw, ch = cells[0][1].size
    sheet = Image.new('RGB', (len(cells) * (cw + 12), 2 * (ch + 26) + 10), bg)
    dr = ImageDraw.Draw(sheet)
    for i, (label, top, mk1, bot, mk2) in enumerate(cells):
        x = i * (cw + 12) + 6
        sheet.paste(top.convert('RGB'), (x, 22))
        sheet.paste(bot.convert('RGB'), (x, 22 + ch + 26))
        for (mk, y0) in ((mk1, 22), (mk2, 22 + ch + 26)):
            cx, cy = mk[0] + x, mk[1] + y0
            dr.line((cx - 7, cy, cx + 7, cy), fill=(220, 0, 140))
            dr.line((cx, cy - 7, cx, cy + 7), fill=(220, 0, 140))
        dr.text((x, 6), 'sample: ' + label, fill=(120, 0, 80))
        dr.text((x, 22 + ch + 8), 'raster: ' + label, fill=(120, 0, 80))
    sheet.save(out_path)
    print('saved', out_path, sheet.size)


def sizes(frame_path, out_path):
    base = _load(frame_path)
    tiles = []
    for px in (48, 96):
        for bgc, name in (((240, 240, 242), 'light'), ((24, 26, 34), 'dark')):
            im = base.resize((px, px), Image.NEAREST)
            tile = Image.new('RGBA', (px, px), bgc + (255,))
            tile.alpha_composite(im)
            tiles.append(('%dpx %s' % (px, name), tile))
    pad = 14
    w = sum(t.width + pad for _, t in tiles) + pad
    h = max(t.height for _, t in tiles) + 40
    sheet = Image.new('RGB', (w, h), (210, 210, 214))
    dr = ImageDraw.Draw(sheet)
    x = pad
    for label, t in tiles:
        sheet.paste(t.convert('RGB'), (x, 26))
        dr.text((x, 8), label, fill=(150, 0, 0))
        x += t.width + pad
    sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
    sheet.save(out_path)
    print('saved', out_path, sheet.size)


if __name__ == '__main__':
    # rest, mid-lift and peak pairs (sample frame numbers vs raster hello frame numbers)
    compare([
        ('rest', os.path.join(WAVE, 'mascot-wave-frame0.png'),
         os.path.join(OUT, 'frames', 'hello', '000.png'),
         'sample_box', (505, 545, 585, 640)),
        ('mid-lift', os.path.join(WAVE, 'mascot-wave-frame5.png'),
         os.path.join(OUT, 'frames', 'hello', '004.png'),
         'sample', None),
        ('peak', os.path.join(WAVE, 'mascot-wave-frame2.png'),
         os.path.join(OUT, 'frames', 'hello', '006.png'),
         'sample', None),
    ], os.path.join(HERE, '_hello_compare.png'))
    sizes(os.path.join(OUT, 'frames', 'hello', '006.png'),
          os.path.join(HERE, '_hello_sizes.png'))
