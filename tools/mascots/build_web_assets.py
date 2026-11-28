"""Build the web-ready mascot assets from the generator packs.

Run from the repository root:

    python tools/mascots/build_web_assets.py [--out DIR]

Reads tools/mascots/<id>-animations/ and writes src/static/images/mascots/<id>/
for raster, pip and trace: one horizontal sprite sheet per animation, a neutral
still, two preview GIFs for the Settings picker and a normalized manifest.json.

Every mascot is scaled so its neutral body height (the alpha bounding box of
idle-blink frame 0) is 90 px, the shared baseline from docs/MASCOTS.md section 3.
Raster is already 90 px and is passed through untouched; Pip and Trace are
scaled down with the per-mascot method in SCALING.

The output is deterministic: sorted iteration, no timestamps and fixed GIF
settings, so a rebuild produces the same pictures byte for byte.
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

# Downscale method per mascot. None keeps the source pixels untouched (Raster
# is native 90 px and must stay pixel-perfect); 'nearest' samples whole source
# pixels (keeps Pip's 12-colour palette exact); 'lanczos' resamples with
# premultiplied alpha and then thresholds the alpha so edges stay hard.
# Switching a mascot later is a one-line change here plus a rebuild.
SCALING = {'raster': None, 'pip': 'nearest', 'trace': 'lanczos'}

NAMES = {'raster': 'Raster', 'pip': 'Pip', 'trace': 'Trace'}

# The looping idle shown in the Settings picker (docs/MASCOTS.md section 9).
PREVIEW_IDLE = {'raster': 'idle-look-around', 'pip': 'idle-tail-sway', 'trace': 'idle-sway'}

TARGET_BODY_HEIGHT = 90
MARGIN = 2  # transparent margin kept around the union of all frames
ALPHA_CUTOFF = 128  # alpha at/above this counts as content and stays solid
TRANSPARENT_INDEX = 255  # reserved GIF palette slot for transparency

PACKS_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = PACKS_DIR.parent.parent / 'src' / 'static' / 'images' / 'mascots'


def load_pack(pack_dir, mid):
    """Return {animation name: {"frames", "durations_ms", "loop", "start_pose", "end_pose"}}.

    The three packs keep different manifest shapes (raster 'mode'/'frames'/
    'durations_ms', pip 'behavior'/'frames'/'durations_ms', trace
    'behavior'/'frame_durations_ms'/'frames_dir'), so each is read on its own
    terms. Hold frames stay as one PNG plus a duration; nothing is expanded.
    """
    man = json.loads((pack_dir / 'manifest.json').read_text(encoding='utf-8'))
    anims = {}
    for entry in man['animations']:
        if mid == 'trace':
            frames = sorted((pack_dir / entry['frames_dir']).glob('*.png'))
            durations = list(entry['frame_durations_ms'])
            loop = entry['behavior'] == 'loop'
        else:
            frames = [pack_dir / p for p in entry['frames']]
            durations = list(entry['durations_ms'])
            key = 'mode' if mid == 'raster' else 'behavior'
            loop = entry[key] == 'loop'
        if len(frames) != len(durations):
            name = entry['name']
            raise ValueError(f'{mid}/{name}: {len(frames)} frames but {len(durations)} durations')
        anims[entry['name']] = {
            'frames': frames,
            'durations_ms': durations,
            'loop': loop,
            'start_pose': entry['start_pose'],
            'end_pose': entry['end_pose'],
        }
    return anims


def content_bbox(img):
    """Alpha bounding box of the visible content (ignores faint haze)."""
    alpha = np.asarray(img.getchannel('A'))
    ys, xs = np.where(alpha >= ALPHA_CUTOFF)
    if len(xs) == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _resize_soft(img, size, resample):
    """Premultiplied-alpha resize, then threshold the alpha so edges stay hard."""
    arr = np.asarray(img).astype(np.float32) / 255.0
    alpha = arr[..., 3]
    rgb = arr[..., :3] * alpha[..., None]

    def _rs(channel):
        plane = Image.fromarray(channel.astype(np.float32), 'F')
        return np.asarray(plane.resize(size, resample))

    out_a = _rs(alpha)
    out_rgb = np.stack([_rs(rgb[..., i]) for i in range(3)], axis=-1)
    with np.errstate(divide='ignore', invalid='ignore'):
        un = np.maximum(out_a[..., None], 1e-6)
        out_rgb = np.where(out_a[..., None] > 0, out_rgb / un, 0.0)
    solid = out_a * 255.0 >= ALPHA_CUTOFF
    out = np.zeros(out_rgb.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.where(solid[..., None], np.clip(out_rgb * 255.0 + 0.5, 0, 255), 0)
    out[..., 3] = np.where(solid, 255, 0)
    return Image.fromarray(out, 'RGBA')


def _resize_nearest(img, size):
    out = img.resize(size, Image.NEAREST)
    alpha = np.asarray(out.getchannel('A'))
    out.putalpha(Image.fromarray(np.where(alpha >= ALPHA_CUTOFF, 255, 0).astype(np.uint8), 'L'))
    return out


def scale_frame(img, size, method):
    if method is None:
        return img
    if method == 'nearest':
        return _resize_nearest(img, size)
    if method == 'box':
        return _resize_soft(img, size, Image.BOX)
    if method == 'lanczos':
        return _resize_soft(img, size, Image.LANCZOS)
    raise ValueError(f'unknown scaling method {method!r}')


def sprite_sheet(frames, frame_w, frame_h):
    sheet = Image.new('RGBA', (frame_w * len(frames), frame_h))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * frame_w, 0))
    return sheet


def _gif_palette(frames):
    """One palette shared by every frame of a GIF, so colours cannot shimmer.

    Exact when the frames fit in 255 colours (Pip's 12-colour palette does);
    index 255 is reserved for transparency.
    """
    colors = set()
    for frame in frames:
        arr = np.asarray(frame)
        colors.update(map(tuple, arr[arr[..., 3] >= ALPHA_CUTOFF][:, :3].tolist()))
    colors = sorted(colors)
    if len(colors) > 255:
        strip = Image.new('RGB', (len(colors), 1))
        strip.putdata([tuple(c) for c in colors])
        quantized = strip.quantize(colors=255, method=Image.MEDIANCUT)
        used = sorted(set(np.asarray(quantized).ravel().tolist()))
        pal = [tuple(quantized.getpalette()[i * 3:i * 3 + 3]) for i in used]
    else:
        pal = colors
    flat = [c for color in pal for c in color] + [0, 0, 0] * (256 - len(pal))
    return flat


def write_gif(path, frames, durations_ms, loop):
    """Encode a preview GIF: one palette per GIF, hard transparency, fixed settings."""
    flat = _gif_palette(frames)
    pal_img = Image.new('P', (1, 1))
    pal_img.putpalette(flat)
    encoded = []
    for frame in frames:
        indexed = frame.convert('RGB').quantize(palette=pal_img, dither=Image.Dither.NONE)
        indexed = np.asarray(indexed).copy()
        indexed[np.asarray(frame.getchannel('A')) < ALPHA_CUTOFF] = TRANSPARENT_INDEX
        out = Image.fromarray(indexed, 'P')
        out.putpalette(flat)
        encoded.append(out)
    params = {
        'save_all': True,
        'append_images': encoded[1:],
        'duration': list(durations_ms),
        'transparency': TRANSPARENT_INDEX,
        'disposal': 2,
    }
    if loop:
        params['loop'] = 0  # NETSCAPE 0 = repeat forever; omitted = play once
    encoded[0].save(path, **params)


def build_mascot(out_root, mid):
    pack_dir = PACKS_DIR / (mid + '-animations')
    anims = load_pack(pack_dir, mid)
    if 'idle-blink' not in anims:
        raise ValueError(f'{mid}: no idle-blink animation to measure the body from')

    # One shared crop box: the union of every frame's content plus a margin.
    # Every frame of a mascot keeps the same box, so motion is preserved and
    # the feet sit on one baseline. A margin running off the canvas pads with
    # transparency (Raster's antenna touches the top edge).
    union = None
    for anim in anims.values():
        for frame_path in anim['frames']:
            box = content_bbox(Image.open(frame_path))
            if box is None:
                continue
            union = box if union is None else (
                min(union[0], box[0]),
                min(union[1], box[1]),
                max(union[2], box[2]),
                max(union[3], box[3]),
            )
    x0, y0 = union[0] - MARGIN, union[1] - MARGIN
    x1, y1 = union[2] + MARGIN, union[3] + MARGIN

    neutral = Image.open(anims['idle-blink']['frames'][0])
    body = content_bbox(neutral)
    scale = TARGET_BODY_HEIGHT / (body[3] - body[1])
    frame_w = round((x1 - x0) * scale)
    frame_h = round((y1 - y0) * scale)
    size = (frame_w, frame_h)
    method = SCALING[mid]

    out_dir = out_root / mid
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    def render(frame_path):
        img = Image.open(frame_path).convert('RGBA').crop((x0, y0, x1, y1))
        return scale_frame(img, size, method)

    manifest_anims = {}
    still = None
    for name in sorted(anims):
        anim = anims[name]
        frames = [render(p) for p in anim['frames']]
        sprite_sheet(frames, frame_w, frame_h).save(out_dir / (name + '.png'))
        if name == 'idle-blink':
            still = frames[0]
        manifest_anims[name] = {
            'sheet': name + '.png',
            'frames': anim['durations_ms'],
            'loop': anim['loop'],
            'total_ms': sum(anim['durations_ms']),
            'start_pose': anim['start_pose'],
            'end_pose': anim['end_pose'],
        }

    still.save(out_dir / 'still.png')
    still_box = content_bbox(still)
    body_height = still_box[3] - still_box[1]

    preview_idle = PREVIEW_IDLE[mid]
    idle = anims[preview_idle]
    write_gif(
        out_dir / 'preview-idle.gif',
        [render(p) for p in idle['frames']],
        idle['durations_ms'],
        loop=True,
    )
    hello = anims['hello']
    write_gif(
        out_dir / 'preview-hello.gif',
        [render(p) for p in hello['frames']],
        hello['durations_ms'],
        loop=False,
    )

    manifest = {
        'id': mid,
        'name': NAMES[mid],
        'frame_width': frame_w,
        'frame_height': frame_h,
        'body_height': body_height,
        'animations': manifest_anims,
    }
    with open(out_dir / 'manifest.json', 'w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write('\n')

    label = method or 'untouched'
    print(f'{mid}: {len(anims)} animations, frame {frame_w}x{frame_h}, '
          f'scale {scale:.4f} ({label}), body {body_height}px')


def main():
    parser = argparse.ArgumentParser(description='Build the mascot web assets.')
    parser.add_argument(
        '--out',
        type=Path,
        default=DEFAULT_OUT,
        help='output directory (default: src/static/images/mascots)',
    )
    args = parser.parse_args()
    for mid in ('raster', 'pip', 'trace'):
        build_mascot(args.out, mid)


if __name__ == '__main__':
    main()
