"""Contact-sheet tool: zoom crops of pose/frame PNGs for visual inspection.

Usage:  python contact_sheet.py out.png 10 R_r0 R_r2 R_r4 R_r6 L_r0 L_r2 L_r4 L_r6
        (names resolve in source/pose_art/, frames/<name>/NNN.png, or gifs/ as .gif)
"""
from PIL import Image, ImageDraw
import sys
import os
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def resolve(name):
    p = os.path.join(HERE, 'pose_art', name + '.png')
    if os.path.exists(p):
        return p
    if '/' in name:
        clip, frame = name.split('/', 1)
        p = os.path.join(ROOT, 'raster-animations', 'frames', clip, frame + '.png')
        if os.path.exists(p):
            return p
    p = os.path.join(ROOT, 'raster-animations', 'frames', name)
    if os.path.isdir(p):
        return sorted(glob.glob(os.path.join(p, '*.png')))
    p = os.path.join(ROOT, 'raster-animations', name)
    if os.path.exists(p):
        return p
    return name


def sheet(out, zoom, names, crop=None, cols=4, full=False):
    imgs = []
    for n in names:
        r = resolve(n)
        if isinstance(r, list):
            r = r[0]
        im = Image.open(r).convert('RGBA')
        if full:
            pass
        elif crop:
            im = im.crop(crop)
        else:
            bb = im.getbbox()
            if bb:
                pad = 2
                im = im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad),
                              min(im.width, bb[2] + pad), min(im.height, bb[3] + pad)))
        imgs.append((n, im))
    w = max(im.width for _, im in imgs) * zoom
    h = max(im.height for _, im in imgs) * zoom
    rows = (len(imgs) + cols - 1) // cols
    sh = Image.new('RGB', (cols * (w + 10), rows * (h + 22)), (232, 232, 236))
    dr = ImageDraw.Draw(sh)
    for i, (n, im) in enumerate(imgs):
        im = im.resize((im.width * zoom, im.height * zoom), Image.NEAREST)
        cx = (i % cols) * (w + 10) + 5
        cy = (i // cols) * (h + 22) + 16
        bg = Image.new('RGBA', im.size, (232, 232, 236, 255))
        bg.alpha_composite(im)
        sh.paste(bg.convert('RGB'), (cx, cy))
        dr.text((cx, cy - 13), n, fill=(180, 0, 0))
    sh.save(out)
    print('saved', out, sh.size)


if __name__ == '__main__':
    out = sys.argv[1]
    zoom = int(sys.argv[2])
    names = sys.argv[3:]
    cols = 4
    full = False
    crop = None
    if names and names[0].startswith('cols='):
        cols = int(names[0].split('=')[1])
        names = names[1:]
    if names and names[0] == 'full':
        full = True
        names = names[1:]
    if names and names[0].startswith('crop='):
        crop = tuple(int(v) for v in names[0][5:].split(','))
        names = names[1:]
    sheet(out, zoom, names, cols=cols, full=full, crop=crop)
