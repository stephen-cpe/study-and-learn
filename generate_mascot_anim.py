#!/usr/bin/env python3
"""
Generate animated mascot frames, sprite sheets, and GIFs for the Study Robot.

Uses the original mascot-robot.png as exact base reference.  Creates
variants for idle, busy (3 escalation stages), happy, error, talk, and
wave states.

Cross-platform: resolves paths relative to this script's location, so the
script works identically on Windows 11 (dev) and Ubuntu/Linux (prod).

Frame plan (mascot animation polish):
  IDLE   = 14 frames @ 250ms  (sway + chest LED chase + 3-frame blink + pulse)
  BUSY_A = 14 frames @ 150ms  (scanline sweep, green eyes  — parsing stage)
  BUSY_B = 14 frames @ 150ms  (scanline sweep, amber eyes — generating stage)
  BUSY_C = 14 frames @ 150ms  (scanline sweep, red eyes   — final intense)
  HAPPY  = 14 frames @ 220ms  (anticipation squash + hop + diamond sparkles)
  ERROR  = 14 frames @ 220ms  (sag + red eye/antenna blink + dim chest + warns)
  TALK   = 12 frames @ 110ms  (bounce + mouth flap + chest heartbeat + antenna)
  WAVE   = 16 frames @ 140ms  (squash + whole right-arm swings up from shoulder)

All animations share the same 759x759 canvas and transparent
palette-index-255 trick so they composite cleanly over the cyberpunk UI.
The base ``mascot-robot.png`` is never re-painted – error frames still
recognisably show the original mascot (we communicate "error" through
choreography, not by drawing a different robot on top).

Outputs per state (into src/static/images/mascots/<state>/):
  mascot-<state>.gif              animated GIF (legacy fallback)
  mascot-<state>-sprite.png       1-row sprite sheet for CSS steps()
  mascot-<state>-frame<N>.png     individual frames (debugging)
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
IMAGES_DIR = SCRIPT_DIR / 'src' / 'static' / 'images'
BASE_PATH = IMAGES_DIR / 'mascots' / 'mascot-robot.png'
MASCOTS_DIR = IMAGES_DIR / 'mascots'
STATE_DIRS = {
    'idle': MASCOTS_DIR / 'idle',
    'busy': MASCOTS_DIR / 'busy',
    'busyB': MASCOTS_DIR / 'busyB',
    'busyC': MASCOTS_DIR / 'busyC',
    'happy': MASCOTS_DIR / 'happy',
    'error': MASCOTS_DIR / 'error',
    'talk': MASCOTS_DIR / 'talk',
    'wave': MASCOTS_DIR / 'wave',
}
for _state_dir in STATE_DIRS.values():
    _state_dir.mkdir(parents=True, exist_ok=True)
MASCOTS_DIR.mkdir(parents=True, exist_ok=True)

# Hardcoded bounding boxes derived from analysis of mascot-robot.png
EYE_LEFT = (305, 290, 360, 357)
EYE_RIGHT = (453, 289, 505, 357)
CHEST_YELLOW = (360, 475, 378, 490)
CHEST_BLUE = (394, 475, 413, 490)
CHEST_GREEN = (425, 444, 444, 491)
CHEST_LIGHTS = [
    ('yellow', CHEST_YELLOW),
    ('blue', CHEST_BLUE),
    ('green', CHEST_GREEN),
]
ANTENNA_BALL = (348, 70, 417, 119)
# Face screen white area (for scanline sweep)
SCREEN = (243, 210, 565, 397)
DARK_EYE = (5, 10, 25, 255)
HALF_EYE_GRAY = (58, 66, 78, 255)

# Canvas size (square) – every frame is 759x759 to match the source PNG.
CANVAS_SIZE = (759, 759)

# Animation tuning
IDLE_FRAMES = 14
BUSY_FRAMES = 14
HAPPY_FRAMES = 14
ERROR_FRAMES = 14
TALK_FRAMES = 12
WAVE_FRAMES = 16


# --------------------------------------------------------------------------- #
# Frame primitives (small reusable image operations)                          #
# --------------------------------------------------------------------------- #
def load_base() -> Image.Image:
    img = Image.open(str(BASE_PATH)).convert('RGBA')
    print(f"Loaded base: {img.size}")
    return img


def paste_with_bob(base: Image.Image, shift: int) -> Image.Image:
    """Return a copy of ``base`` shifted vertically by ``shift`` pixels.

    The bob is intentionally symmetric around 0 and is small (a few pixels)
    so the chest lights and antenna stay aligned with the rest of the
    artwork when previewed at 120x120.
    """
    canvas = Image.new('RGBA', base.size, (0, 0, 0, 0))
    canvas.paste(base, (0, shift), base)
    return canvas


def antenna_tint(base: Image.Image, factor: float = 1.0) -> Image.Image:
    """Apply a barely-perceptible antenna-brightness change.

    Used as a per-frame *uniqueness injector*.  Even a 0.5% change in
    antenna brightness is invisible at 120x120 display size but produces
    a different pixel hash, preventing the GIF optimizer from merging
    otherwise-identical frames.  ``factor=1.0`` is a no-op.
    """
    if factor == 1.0:
        return base
    return antenna_glow(base, factor)



def blink(base: Image.Image) -> Image.Image:
    """Eyes powered off: paint both eye rectangles with the dark display color."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    draw.rectangle(EYE_LEFT, fill=DARK_EYE)
    draw.rectangle(EYE_RIGHT, fill=DARK_EYE)
    return img


def antenna_glow(base: Image.Image, factor: float = 1.6) -> Image.Image:
    """Brighten the antenna ball.  Only blue-ish pixels are touched so the
    surrounding casing keeps its original hue."""
    img = base.copy()
    arr = np.array(img)
    x0, y0, x1, y1 = ANTENNA_BALL
    region = arr[y0:y1, x0:x1]
    mask = (region[:, :, 2] > 100) & (region[:, :, 0] < 100) & \
           (region[:, :, 1] < 150) & (region[:, :, 3] > 200)
    for c in range(3):
        region[:, :, c][mask] = np.clip(
            region[:, :, c][mask].astype(int) * factor, 0, 255
        ).astype(np.uint8)
    arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)


def chest_cycle(base: Image.Image, active: str = 'yellow',
                dim_factor: float = 0.4, boost: float = 1.3) -> Image.Image:
    """One chest light bright, the others dimmed.  ``active`` is the key
    from :data:`CHEST_LIGHTS`."""
    img = base.copy()
    arr = np.array(img)
    for name, (x0, y0, x1, y1) in CHEST_LIGHTS:
        region = arr[y0:y1, x0:x1]
        if name == active:
            region = np.clip(region.astype(int) * boost, 0, 255).astype(np.uint8)
        else:
            region = np.clip(region.astype(int) * dim_factor, 0, 255).astype(np.uint8)
        arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)


def all_chest_on(base: Image.Image, boost: float = 1.4) -> Image.Image:
    """All three chest lights glowing (used by happy state)."""
    img = base.copy()
    arr = np.array(img)
    for _name, (x0, y0, x1, y1) in CHEST_LIGHTS:
        region = arr[y0:y1, x0:x1]
        region = np.clip(region.astype(int) * boost, 0, 255).astype(np.uint8)
        arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)


def sparkle_eyes(base: Image.Image) -> Image.Image:
    """Brighter eyes with a small white sparkle cluster at the centre."""
    img = base.copy()
    arr = np.array(img)
    for (x0, y0, x1, y1) in (EYE_LEFT, EYE_RIGHT):
        region = arr[y0:y1, x0:x1]
        g = region[:, :, 1].astype(int)
        region[:, :, 1] = np.clip(g * 1.4, 0, 255).astype(np.uint8)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        for dx, dy in [(-6, -6), (6, -6), (-6, 6), (6, 6), (0, 0), (-3, 3), (3, -3)]:
            sx, sy = cx + dx, cy + dy
            if y0 < sy < y1 and x0 < sx < x1:
                arr[sy, sx] = (255, 255, 255, 255)
    return Image.fromarray(arr)


# --------------------------------------------------------------------------- #
# Overlay helpers (transparent pixels on the canvas, around the mascot)        #
# --------------------------------------------------------------------------- #
def _draw_pixel(draw: ImageDraw.ImageDraw, x: float, y: float,
                color: tuple[int, int, int, int], size: int = 4) -> None:
    half = size // 2
    draw.rectangle((x - half, y - half, x + half, y + half), fill=color)


def add_sparkles(base: Image.Image, t: float, count: int = 6,
                 color: tuple[int, int, int, int] = (255, 255, 200, 255),
                 radius: tuple[float, float] = (320, 360)) -> Image.Image:
    """Scatter a small ring of pixels around the mascot.  ``t`` is the
    frame index 0..1 used to rotate and fade the particles."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    for i in range(count):
        angle = 2 * math.pi * (i / count + t)
        r = radius[0] + (radius[1] - radius[0]) * (0.5 + 0.5 * math.sin(t * math.pi * 2 + i))
        cx, cy = 380, 360  # near mascot centre
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle) * 0.5
        _draw_pixel(draw, x, y, color, size=5)
    return img


def add_rising_particles(base: Image.Image, t: float,
                         count: int = 6) -> Image.Image:
    """Stars/hearts/cyan squares rising from the mascot's base.

    ``t`` is the loop progress 0..1.  The mascot "exhales" particles every
    loop, which combined with the bounce is the happy signature.
    """
    img = base.copy()
    draw = ImageDraw.Draw(img)
    palette = [
        (126, 231, 135, 255),  # green
        (255, 230, 109, 255),  # yellow
        (255, 132, 170, 255),  # pink heart-ish
        (130, 215, 255, 255),  # cyan sparkle
    ]
    base_y = 700
    top_y = 120
    for i in range(count):
        phase = (t + i / count) % 1.0
        x = 380 + 90 * math.sin(2 * math.pi * (i / count + t * 1.3))
        y = base_y - phase * (base_y - top_y)
        size = 5
        color = palette[i % len(palette)]
        _draw_pixel(draw, x, y, color, size=size)
    return img


def add_gear_orbit(base: Image.Image, t: float, count: int = 3) -> Image.Image:
    """A small cluster of cyan squares orbiting the mascot's head, used as
    the busy state signature."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    cx, cy = 380, 360
    radius = 230
    for i in range(count):
        angle = 2 * math.pi * (i / count + t)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle) * 0.45
        # draw a small 3x3 plus shape to read like a "gear tooth"
        for dx, dy in ((0, 0), (-6, 0), (6, 0), (0, -6), (0, 6)):
            _draw_pixel(draw, x + dx, y + dy, (0, 180, 216, 255), size=4)
    return img


# --------------------------------------------------------------------------- #
# Error-state helpers (preserve the base mascot, choreograph the failure)     #
# --------------------------------------------------------------------------- #
def red_eyes(base: Image.Image) -> Image.Image:
    """Fill both eye rectangles with solid red – the error-state "red eye"
    blink.  This is the visual inverse of :func:`blink` (which fills with
    dark): we fill with red so the eyes flash red, then alternate back
    to the original green on the next frame.  The rest of the mascot's
    pixels are untouched."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    red = (255, 70, 80, 255)
    draw.rectangle(EYE_LEFT, fill=red)
    draw.rectangle(EYE_RIGHT, fill=red)
    return img


def red_antenna(base: Image.Image) -> Image.Image:
    """Tint the antenna ball red for the error-state blink.

    Only blue-ish pixels in the antenna region are affected (same mask
    as :func:`antenna_glow`), so the surrounding casing keeps its
    original colour.  The blue channel is swapped to red by
    cross-multiplying: R←R×2.5, G←0, B←0 (clamped).  This preserves
    the alpha channel and the white highlights at the antenna's edge."""
    img = base.copy()
    arr = np.array(img)
    x0, y0, x1, y1 = ANTENNA_BALL
    region = arr[y0:y1, x0:x1]
    mask = (region[:, :, 2] > 100) & (region[:, :, 0] < 100) & \
           (region[:, :, 1] < 150) & (region[:, :, 3] > 200)
    # Swap blue to red: set R high, G and B to 0 in masked pixels.
    region[:, :, 0][mask] = np.clip(
        region[:, :, 0][mask].astype(int) * 2.5, 0, 255
    ).astype(np.uint8)
    region[:, :, 1][mask] = 0
    region[:, :, 2][mask] = 0
    arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)


def dim_chest(base: Image.Image, factor: float = 0.18) -> Image.Image:
    """All three chest lights dimmed to ``factor`` (default ~18%) – the
    mascot is "off".  The yellow/blue/green tints remain so the lights
    are still visible as faint shapes; we are not erasing them."""
    img = base.copy()
    arr = np.array(img)
    for _name, (x0, y0, x1, y1) in CHEST_LIGHTS:
        region = arr[y0:y1, x0:x1]
        region = np.clip(region.astype(int) * factor, 0, 255).astype(np.uint8)
        arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)


def red_chest_flicker(base: Image.Image, strength: float = 1.6) -> Image.Image:
    """Rare error-state chest flicker: dim everything then briefly
    brightens all three lights at a red-tinted level.  Used on 1-2
    beats of the loop to make the error state feel glitchy."""
    img = dim_chest(base, factor=0.18)
    arr = np.array(img)
    # Tint the chest area toward red: pull G and B channels down.
    for _name, (x0, y0, x1, y1) in CHEST_LIGHTS:
        region = arr[y0:y1, x0:x1]
        region[:, :, 0] = np.clip(region[:, :, 0] * strength, 0, 255).astype(np.uint8)
        region[:, :, 1] = (region[:, :, 1] * 0.4).astype(np.uint8)
        region[:, :, 2] = (region[:, :, 2] * 0.4).astype(np.uint8)
        arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)


def add_warning_particles(base: Image.Image, t: float, count: int = 4) -> Image.Image:
    """Slow red/orange warning squares that drift horizontally around
    the mascot's mid-line.  This is the error-state signature – unlike
    the busy scanline (on-screen) or the happy rising particles
    (multi-coloured, upward), these are red/orange and drift sideways
    at half the speed of the busy orbit.

    ``t`` is loop progress 0..1.
    """
    img = base.copy()
    draw = ImageDraw.Draw(img)
    palette = [
        (255, 80, 80, 255),    # red
        (255, 130, 60, 255),   # orange
        (255, 200, 80, 255),   # amber
    ]
    # Particles drift horizontally around the mascot's head/shoulders.
    cy = 360
    radius_x = 250
    radius_y = 100
    for i in range(count):
        # Slow horizontal drift, gentle vertical bob.
        x = 380 + radius_x * math.cos(2 * math.pi * (i / count + t * 0.5))
        y = cy + radius_y * math.sin(2 * math.pi * (i / count + t * 0.5))
        # A tiny 3x3 plus shape, like a glitch/warning pixel.
        colour = palette[i % len(palette)]
        for dx, dy in ((0, 0), (-4, 0), (4, 0), (0, -4), (0, 4)):
            _draw_pixel(draw, x + dx, y + dy, colour, size=3)
    return img


# --------------------------------------------------------------------------- #
# New effect helpers (v2 choreography)                                        #
# --------------------------------------------------------------------------- #
def recolor_eyes(base: Image.Image, rgb: tuple) -> Image.Image:
    """Recolour both eye rectangles' green pixels toward ``rgb``."""
    img = base.copy()
    arr = np.array(img)
    for (x0, y0, x1, y1) in (EYE_LEFT, EYE_RIGHT):
        # Expand slightly to catch anti-aliased fringe
        rx0, ry0 = max(0, x0 - 6), max(0, y0 - 6)
        rx1, ry1 = min(759, x1 + 6), min(759, y1 + 6)
        region = arr[ry0:ry1, rx0:rx1]
        r = region[:, :, 0].astype(int)
        g = region[:, :, 1].astype(int)
        b = region[:, :, 2].astype(int)
        mask = (g > 100) & (r < 110) & (b < 130) & (region[:, :, 3] > 150)
        if not mask.any():
            continue
        lum = (r * 0.3 + g * 0.6 + b * 0.1) / 255.0
        for c, w in ((0, rgb[0]), (1, rgb[1]), (2, rgb[2])):
            ch = region[:, :, c].astype(int)
            ch[mask] = np.clip(w * lum[mask] + ch[mask] * 0.08, 0, 255).astype(np.uint8)
            region[:, :, c] = ch
        arr[ry0:ry1, rx0:rx1] = region
    return Image.fromarray(arr)


def scanline_sweep(base: Image.Image, t: float, rgb: tuple) -> Image.Image:
    """A horizontal bright band sweeping down the face screen."""
    img = base.copy()
    arr = np.array(img)
    x0, y0, x1, y1 = SCREEN
    band_h = 24
    span = y1 - y0 - band_h
    yy = int(y0 + (t % 1.0) * span)
    region = arr[yy:yy + band_h, x0:x1]
    vis = region[:, :, 3] > 150
    boost = np.clip(region[:, :, :3].astype(int) * 1.12 + 20, 0, 255).astype(np.uint8)
    region[:, :, :3][vis] = boost[vis]
    arr[yy:yy + band_h, x0:x1] = region
    # 3px tinted leading edge
    edge = arr[yy:yy + 3, x0:x1]
    evis = edge[:, :, 3] > 150
    e = edge[:, :, :3].astype(int)
    for c in range(3):
        e[:, :, c] = np.clip(e[:, :, c] * 0.25 + rgb[c] * 0.75, 0, 255)
    edge[:, :, :3][evis] = e[evis]
    arr[yy:yy + 3, x0:x1] = edge
    return Image.fromarray(arr)


def diamond_sparkle(base: Image.Image, x: int, y: int, alpha: float = 1.0) -> Image.Image:
    """Small diamond twinkle (NOT a plus/cross — that reads as a
    sniper crosshair at 120px).  Used by the happy state."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    a = int(230 * alpha)
    s = 4 + int(3 * alpha)
    draw.rectangle((x - s // 2, y - s // 2, x + s // 2, y + s // 2),
                    fill=(255, 255, 255, a))
    return img


def paste_squash(base: Image.Image, dy: int, sx: float = 1.0, sy: float = 1.0) -> Image.Image:
    """Bottom-centre anchored squash/stretch: feet stay planted."""
    if abs(sx - 1) < 0.004 and abs(sy - 1) < 0.004:
        return paste_with_bob(base, dy)
    arr = np.array(base)
    alphas = arr[:, :, 3]
    ys, xs = np.where(alphas > 8)
    if len(ys) == 0:
        return paste_with_bob(base, dy)
    anchor_x = (xs.min() + xs.max()) / 2.0
    anchor_y = ys.max()
    nw = max(2, int(759 * sx))
    nh = max(2, int(759 * sy))
    scaled = base.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', base.size, (0, 0, 0, 0))
    px = int(round(anchor_x - anchor_x * sx))
    py = int(round(anchor_y - anchor_y * sy))
    canvas.paste(scaled, (px, py), scaled)
    return paste_with_bob(canvas, dy)


# Right-arm chain geometry (probed from mascot-robot.png):
#   mitt (y441-499), wrist+silver forearm (y500-548), elbow ring (y558-596)
#   The bright-blue block below (y603+) is the FOOT — excluded.
#   x-window starts at 482: torso edge columns (x480-481) must be excluded
#   or they swing with the arm (diagonal "line" artifact) and leave a ghost
#   outline in the torso ("spirit" residue).
ARM_CHAIN = (482, 435, 575, 599)
SHOULDER = (543, 448)


def _arm_chain_mask(arr: np.ndarray) -> np.ndarray:
    """Arm pixels incl. the base art's AA fringe (alpha>=15).
    Threshold justification: within the arm window the artwork's soft
    fringe sits at alpha 18-40, while anything below 15 is pure background.
    The mask drives both extraction AND clearing, so missing fringe leaves
    faint 'spirit' lines behind once the arm swings away."""
    x0, y0, x1, y1 = ARM_CHAIN
    m = np.zeros(arr.shape[:2], bool)
    win = arr[y0:y1 + 1, x0:x1 + 1]
    m[y0:y1 + 1, x0:x1 + 1] = win[:, :, 3] >= 15
    return m


def swing_arm(base: Image.Image, angle_deg: float) -> Image.Image:
    """Rotate ALL right-arm segments about the shoulder pivot.

    POSITIVE angle = arm swings OUTWARD (away from the body, screen-right).
    Internal padding: rotation happens on an expanded canvas so the swung
    arm can never clip, then the canvas is restored to 759x759.
    """
    arr = np.array(base)
    mask = _arm_chain_mask(arr)
    px, py = SHOULDER
    arm_only = arr.copy()
    arm_only[~mask] = 0
    cleared = arr.copy()
    cleared[mask] = 0
    pad = 200
    h, w = arm_only.shape[:2]
    padded = np.zeros((h + 2 * pad, w + 2 * pad, 4), np.uint8)
    padded[pad:pad + h, pad:pad + w] = arm_only
    rot = np.array(Image.fromarray(padded).rotate(
        angle_deg, resample=Image.BICUBIC, center=(px + pad, py + pad)))
    rot = rot[pad:pad + h, pad:pad + w]
    # Kill sub-visible AA dust (alpha<=40) from bicubic resampling.
    rot[rot[:, :, 3] <= 40] = 0
    out = Image.fromarray(cleared)
    out.alpha_composite(Image.fromarray(rot))
    result = np.array(out)
    # Final guard: nuke any pixel under 6% opacity anywhere in the frame.
    result[result[:, :, 3] <= 15] = 0
    return Image.fromarray(result)


# --------------------------------------------------------------------------- #
# GIF preparation / sprite sheet helpers                                      #
# --------------------------------------------------------------------------- #
def _prepare_frame_for_gif(frame: Image.Image) -> Image.Image:
    """Convert an RGBA frame to a P-mode frame with a transparent background.

    Why this is non-trivial:
      After ``quantize()``, Pillow's adaptive palette does NOT guarantee
      that palette index 0 will be the most common colour (the
      background).  Saving with ``transparency=0`` would then make some
      near-white palette entry transparent while the actual background
      pixels stay opaque.

    The reliable approach:
      1. Quantize the RGBA image directly to a 255-colour palette.  This
         leaves palette index 255 unused.
      2. Build the alpha mask from the source frame (255 where alpha < 128).
      3. ``paste(255, mask=mask)`` writes palette index 255 at every
         originally-transparent location.
      4. Save with ``transparency=255`` and ``disposal=2`` so each frame
         clears to the background before the next is drawn.
    """
    if frame.mode == 'P':
        return frame
    if frame.mode != 'RGBA':
        frame = frame.convert('RGBA')

    p_frame = frame.quantize(colors=255)
    alpha = frame.getchannel('A')
    transparent_mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
    p_frame.paste(255, mask=transparent_mask)
    return p_frame


def create_sprite_sheet(frames: list[Image.Image], filename: str,
                        out_dir: Path = None) -> str:
    if not frames:
        return ''
    target_dir = Path(out_dir) if out_dir is not None else MASCOTS_DIR
    w, h = frames[0].size
    sheet = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * w, 0), frame)
    out_path = os.path.join(str(target_dir), filename)
    sheet.save(out_path, 'PNG')
    print(f"Saved sprite sheet: {out_path} ({len(frames)} frames, size {sheet.size})")
    return out_path


def create_gif(frames: list[Image.Image], filename: str,
               duration: int = 200, out_dir: Path = None) -> str:
    target_dir = Path(out_dir) if out_dir is not None else MASCOTS_DIR
    out_path = os.path.join(str(target_dir), filename)
    prepared = [_prepare_frame_for_gif(f) for f in frames]
    prepared[0].save(
        out_path,
        save_all=True,
        append_images=prepared[1:],
        duration=duration,
        loop=0,
        transparency=255,
        disposal=2,
    )
    print(f"Saved GIF: {out_path} ({len(frames)} frames @ {duration}ms)")
    return out_path


def save_individual_frames(frames: list[Image.Image], prefix: str,
                           out_dir: Path = None) -> None:
    target_dir = Path(out_dir) if out_dir is not None else MASCOTS_DIR
    for i, frame in enumerate(frames):
        out = target_dir / f'{prefix}-frame{i}.png'
        frame.save(out)


# --------------------------------------------------------------------------- #
# Animation choreography                                                      #
# --------------------------------------------------------------------------- #
def build_idle_frames(base: Image.Image) -> list[Image.Image]:
    """14 unique frames – sway + chest LED chase + 3-frame blink + pulse.

    The blink is staged like the original GIF: wink (one eye half-close)
    → full dark (both eyes, screen-off look) → half-gray recovery → open.
    This reads as a natural blink at 120px, unlike the old single-frame
    wink which looked like a twitch.
    """
    n = IDLE_FRAMES
    frames: list[Image.Image] = []
    for i in range(n):
        frame = base.copy()
        order = ('yellow', 'blue', 'green')
        frame = chest_cycle(frame, order[i % 3], dim_factor=0.4, boost=1.3)
        if i in (6, 13):
            frame = antenna_glow(frame, 1.35)
        # 3-frame blink sequence (frames 8-10)
        if i == 8:
            # wink: right eye lower half gray
            img = frame.copy()
            draw = ImageDraw.Draw(img)
            x0, y0, x1, y1 = EYE_RIGHT
            cut = y0 + (y1 - y0) // 2
            draw.rectangle((x0, cut, x1, y1), fill=HALF_EYE_GRAY)
            frame = img
        elif i == 9:
            # full close: both eyes dark (screen-off)
            frame = blink(frame)
        elif i == 10:
            # half recovery: both eyes bottom half gray
            img = frame.copy()
            draw = ImageDraw.Draw(img)
            for (x0, y0, x1, y1) in (EYE_LEFT, EYE_RIGHT):
                cut = y0 + (y1 - y0) // 2
                draw.rectangle((x0, cut, x1, y1), fill=HALF_EYE_GRAY)
            frame = img
        # Antenna uniqueness nudge for frames that don't already change it.
        # Without this, the GIF optimizer merges similar frames and the
        # user sees fewer frames than intended.
        if i not in (6, 13):
            factors = [1.000, 0.985, 1.020, 0.992, 1.010, 0.995,
                       1.000, 1.005, 0.998, 1.000, 1.003, 0.997,
                       1.008, 1.000]
            factor = factors[i]
            if factor != 1.0:
                frame = antenna_glow(frame, factor)
        frames.append(paste_with_bob(frame, 0))
    return frames


def build_busy_frames(base: Image.Image, variant: str = 'a') -> list[Image.Image]:
    """14 frames – screen scanline sweep + LED chase + micro-bob.

    Three variants escalate the visual intensity so a 45-90 min job
    doesn't look stuck on the same loop:

    a = green eyes, 1 scan/loop   (parsing stage — calm)
    b = amber eyes, 2 scans/loop  (generating stage — warming up)
    c = red eyes, 3 scans/loop     (final intense stage — almost done)

    The scanline sweeps DOWN the face screen (CRT checking), eyes are
    recoloured per variant, and chest LEDs chase.  No more floating
    orbit squares (they read as noise at 120px).
    """
    eye_rgb = {'a': (40, 225, 100), 'b': (255, 190, 60),
               'c': (255, 70, 80)}[variant]
    scan_speed = {'a': 1, 'b': 2, 'c': 3}[variant]
    n = BUSY_FRAMES
    dy = [0, -1, -1, 0, 0, 1, 1, 0, 0, -1, -1, 0, 0, 1]
    frames: list[Image.Image] = []
    for i in range(n):
        frame = base.copy()
        frame = recolor_eyes(frame, eye_rgb)
        scan_t = (i / n) * scan_speed
        frame = scanline_sweep(frame, scan_t, eye_rgb)
        active = ('yellow', 'blue', 'green')[i % 3]
        frame = chest_cycle(frame, active, dim_factor=0.25, boost=1.6)
        if i % 2:
            frame = antenna_glow(frame, 1.2)
        frame = paste_with_bob(frame, dy[i])
        frames.append(frame)
    return frames


def build_happy_frames(base: Image.Image) -> list[Image.Image]:
    """14 frames – anticipation squash → hop with diamond sparkles → land.

    The happy signature is "celebratory": a deep anticipation squash
    (sy 0.88, like crouching before a jump), then a bouncy hop with
    rising particles, then a land squash.  Sparkles are small diamond
    dots (NOT plus-shaped — a plus reads as a sniper crosshair at 120px).
    All three chest lights brighten during the hop.
    """
    pose = [
        # (dy, sx, sy, sparkle_phase)
        (2, 0.965, 0.900, 0.0),    # 0  anticipation squash
        (1, 0.955, 0.885, 0.0),     # 1  deeper squash
        (-2, 1.045, 1.085, 0.15),   # 2  launch (stretch)
        (-6, 1.025, 1.040, 0.30),   # 3  rising
        (-10, 1.000, 1.000, 0.45),  # 4  apex
        (-10, 1.000, 1.000, 0.55),  # 5  apex hold
        (-6, 1.020, 1.025, 0.70),   # 6  falling
        (-2, 1.020, 1.020, 0.85),   # 7  touchdown
        (3, 0.960, 0.890, 0.0),     # 8  land squash
        (1, 1.010, 1.000, 0.0),     # 9  recover
        (0, 1.000, 1.000, 0.0),     # 10 rest
        (0, 1.000, 1.000, 0.0),     # 11 rest
        (0, 1.000, 1.000, 0.0),     # 12 rest
        (0, 1.000, 1.000, 0.0),     # 13 rest
    ]
    sparkle_spots = [(320, 240), (470, 330), (400, 190), (520, 250)]
    frames: list[Image.Image] = []
    for i, (dyi, sxi, syi, sph) in enumerate(pose):
        frame = base.copy()
        frame = recolor_eyes(frame, (45, 235, 100))
        frame = all_chest_on(frame, boost=1.45)
        if sph:
            frame = add_rising_particles(frame, sph, count=5)
        if i in (3, 5):
            spot = sparkle_spots[i % len(sparkle_spots)]
            frame = diamond_sparkle(frame, spot[0], spot[1], 1.0)
        # Per-frame antenna nudge to prevent GIF optimizer merging
        # otherwise-similar rest frames (10-13 are all identical base).
        ant_factors = [1.000, 1.000, 1.000, 1.015, 1.025, 1.030,
                       1.020, 1.010, 1.000, 0.995, 1.008, 1.012, 0.998, 1.005]
        if ant_factors[i] != 1.0:
            frame = antenna_glow(frame, ant_factors[i])
        frame = paste_squash(frame, dyi, sxi, syi)
        frames.append(frame)
    return frames


def build_error_frames(base: Image.Image) -> list[Image.Image]:
    """14 unique frames – drooping bob + red↔green eye blink +
    blue↔red antenna blink + dimmed chest + slow red/orange warning
    particles.

    Error signature is "distressed, glitchy":
      * Vertical bob drops down by 0-3 px (head sag) then a small
        recovery bounce back up to 0/-1.
      * Eyes alternate between their original green (even frames)
        and solid red (odd frames) – a red↔green blink that signals
        error while preserving the base green-eye colour on every
        other frame so the mascot stays recognisable.
      * Antenna alternates between its original blue (even frames)
        and red-tinted (odd frames) – a blue↔red blink that
        mirrors the eye blink.
      * Chest lights are dimmed to 18%; 2 of the 14 frames briefly
        show a red chest flicker.
      * 4 red/orange warning particles drift horizontally around the
        mascot at half the speed of the busy gear orbit.

    The base ``mascot-robot.png`` is never re-painted – we layer these
    error cues on top of the original artwork so the mascot is still
    recognisably the same character, just obviously in trouble.
    """
    # Asymmetric bob: drop down (head sag) then partial recovery.
    bob = [0, 1, 2, 3, 2, 1, 0, -1, 0, 1, 2, 1, 0, -1]
    # Indices that get a red chest flicker (rare, glitchy)
    flicker_indices = {4, 9}
    frames: list[Image.Image] = []
    for i, shift in enumerate(bob):
        # Start with the bobbed base.
        frame = paste_with_bob(base, shift)
        # Eyes: red↔green blink.  Even frames keep original green eyes;
        # odd frames flash red.
        if i % 2 == 1:
            frame = red_eyes(frame)
        # Antenna: blue↔red blink.  Even frames keep original blue
        # antenna; odd frames flash red.
        if i % 2 == 1:
            frame = red_antenna(frame)
        # Dimmed chest, with a rare red flicker on a couple of beats.
        if i in flicker_indices:
            frame = red_chest_flicker(frame)
        else:
            frame = dim_chest(frame, factor=0.18)
        # Slow warning particles.
        t = i / ERROR_FRAMES
        frame = add_warning_particles(frame, t, count=4)
        frames.append(frame)
    return frames


def build_talk_frames(base: Image.Image) -> list[Image.Image]:
    """12 frames – quick bounce + LED heartbeat + antenna blip + eye flicker.

    The talk state plays while the CRT speech bubble types its message.
    Signature: fast vertical bounce (±2px), chest LEDs pulse in a
    heartbeat pattern (2 on, 2 off), antenna blips every 3rd frame, and
    eyes brighten on even frames.  Reads as "speaking" without a mouth.
    """
    n = TALK_FRAMES
    dy = [0, -1, -2, -1, 0, 1, 0, -1, -1, 0, 1, 0]
    frames: list[Image.Image] = []
    for i in range(n):
        frame = base.copy()
        # Heartbeat chest: all LEDs bright on beats 0-1, dim on 2-3
        if i % 4 in (0, 1):
            frame = all_chest_on(frame, boost=1.5)
        else:
            frame = dim_chest(frame, factor=0.7)
        if i % 3 == 0:
            frame = antenna_glow(frame, 1.5)
        if i % 2 == 0:
            frame = recolor_eyes(frame, (40, 225, 95))
        frame = paste_with_bob(frame, dy[i])
        frames.append(frame)
    return frames


def build_wave_frames(base: Image.Image) -> list[Image.Image]:
    """16 frames – anticipation squash → whole right arm swings up from
    the shoulder (mitt beside the head, like the reference video) →
    wave waggles → arm lowers → land → rest.

    The arm chain (mitt + wrist + silver forearm + elbow ring) is a set
    of floating segments in the artwork with deliberate gaps.  All
    segments rotate together about the outer shoulder corner (543, 448)
    so the mitt ends up beside the TV screen's upper-right corner — the
    classic Tamagotchi wave pose.  POSITIVE angles swing outward.
    """
    pose = [
        # (dy, sx, sy, arm_angle)
        (0, 1.000, 1.000, 0),      # 0  neutral
        (3, 0.962, 0.900, 0),      # 1  anticipation squash
        (0, 1.030, 1.060, 30),     # 2  arm starts outward
        (-3, 1.000, 1.000, 70),    # 3  swinging up-out
        (-4, 1.000, 1.000, 95),    # 4  raised: mitt out beside head
        (-3, 1.000, 1.000, 108),   # 5  waggle out
        (-4, 1.000, 1.000, 88),    # 6  waggle in
        (-3, 1.000, 1.000, 110),   # 7
        (-4, 1.000, 1.000, 88),    # 8
        (-2, 1.000, 1.000, 98),    # 9  settle
        (-1, 1.000, 1.000, 50),    # 10 lowering
        (2, 0.990, 0.995, 0),      # 11 land squash, arm docked
        (0, 1.000, 1.000, 0),
        (0, 1.000, 1.000, 0),
        (0, 1.000, 1.000, 0),
        (0, 1.000, 1.000, 0),
    ]
    frames: list[Image.Image] = []
    for (dyi, sxi, syi, ang) in pose:
        frame = base.copy()
        frame = all_chest_on(frame, boost=1.35)
        if ang:
            frame = swing_arm(frame, ang)
        frame = paste_squash(frame, dyi, sxi, syi)
        frames.append(frame)
    return frames


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> None:
    base = load_base()

    states = [
        ('idle',  'mascot-idle',  build_idle_frames(base),       250),
        ('busy',  'mascot-busy',  build_busy_frames(base, 'a'),   150),
        ('busyB', 'mascot-busyB', build_busy_frames(base, 'b'),   150),
        ('busyC', 'mascot-busyC', build_busy_frames(base, 'c'),   150),
        ('happy', 'mascot-happy', build_happy_frames(base),      220),
        ('error', 'mascot-error', build_error_frames(base),      220),
        ('talk',  'mascot-talk',  build_talk_frames(base),       110),
        ('wave',  'mascot-wave',  build_wave_frames(base),       140),
    ]

    for state_key, prefix, frames, duration in states:
        out_dir = STATE_DIRS[state_key]
        print(f"\n=== {state_key} ({len(frames)} frames @ {duration}ms) ===")
        # Sprite sheet (1-row, for CSS steps() playback — primary delivery)
        create_sprite_sheet(frames, f'{prefix}-sprite.png', out_dir)
        # GIF (legacy fallback for browsers without CSS steps() support)
        create_gif(frames, f'{prefix}.gif', duration=duration, out_dir=out_dir)
        # Individual frames (debugging)
        save_individual_frames(frames, prefix, out_dir)

    base.save(os.path.join(str(MASCOTS_DIR), 'mascot-robot-static.png'))
    print("\nDone! Generated sprite sheets, GIFs, and frames in", MASCOTS_DIR)


if __name__ == '__main__':
    main()
