#!/usr/bin/env python3
"""
Generate animated mascot frames and sprite sheets for the Study Robot.
Uses the original mascot-robot.png as exact base reference.
Creates variants for idle animation, processing, happy, and error states.

Cross-platform: resolves paths relative to this script's location, so the
script works identically on Windows 11 (dev) and Ubuntu/Linux (prod).

Frame plan (Sprint 7 mascot animation polish):
  IDLE  = 14 frames @ 250ms  (slow breathing + occasional blink + chest cycle)
  BUSY  = 16 frames @ 140ms  (fast light chase + rapid blink + gear orbit)
  HAPPY = 14 frames @ 220ms  (bouncy hop + eye sparkles + rising particles)
  ERROR = 14 frames @ 220ms  (drooping bob + X-eyes + dimmed chest + slow
                              red/orange warning particle drift)

All four animations share the same 759x759 canvas and the same transparent
palette-index-255 trick so they all composite cleanly over the cyberpunk UI.
The base ``mascot-robot.png`` is never re-painted – error frames still
recognisably show the original mascot (we communicate "error" through
choreography, not by drawing a different robot on top).

All GIFs are written with palette index 255 mapped to fully-transparent
pixels and disposal=2 so every frame clears to the transparent background
before drawing the next.  See ``_prepare_frame_for_gif`` for the rationale.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_PATH = SCRIPT_DIR / 'src' / 'static' / 'images' / 'mascot-robot.png'
OUT_DIR = SCRIPT_DIR / 'src' / 'static' / 'images'
os.makedirs(OUT_DIR, exist_ok=True)

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
DARK_EYE = (5, 10, 25, 255)

# Canvas size (square) – every frame is 759x759 to match the source PNG.
CANVAS_SIZE = (759, 759)

# Animation tuning
IDLE_FRAMES = 14
BUSY_FRAMES = 16
HAPPY_FRAMES = 14
ERROR_FRAMES = 14


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
    the busy gear orbit (cyan, fast) or the happy rising particles
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
        phase = (t + i / count) % 1.0
        # Slow horizontal drift, gentle vertical bob.
        x = 380 + radius_x * math.cos(2 * math.pi * (i / count + t * 0.5))
        y = cy + radius_y * math.sin(2 * math.pi * (i / count + t * 0.5))
        # A tiny 3x3 plus shape, like a glitch/warning pixel.
        colour = palette[i % len(palette)]
        for dx, dy in ((0, 0), (-4, 0), (4, 0), (0, -4), (0, 4)):
            _draw_pixel(draw, x + dx, y + dy, colour, size=3)
    return img


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


def create_sprite_sheet(frames: list[Image.Image], filename: str) -> str:
    if not frames:
        return ''
    w, h = frames[0].size
    sheet = Image.new('RGBA', (w * len(frames), h), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * w, 0), frame)
    out_path = os.path.join(str(OUT_DIR), filename)
    sheet.save(out_path, 'PNG')
    print(f"Saved sprite sheet: {out_path} ({len(frames)} frames, size {sheet.size})")
    return out_path


def create_gif(frames: list[Image.Image], filename: str,
               duration: int = 200) -> str:
    out_path = os.path.join(str(OUT_DIR), filename)
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


def save_individual_frames(frames: list[Image.Image], prefix: str) -> None:
    for i, frame in enumerate(frames):
        out = OUT_DIR / f'{prefix}-frame{i}.png'
        frame.save(out)


# --------------------------------------------------------------------------- #
# Animation choreography                                                      #
# --------------------------------------------------------------------------- #
def build_idle_frames(base: Image.Image) -> list[Image.Image]:
    """14 unique frames – slow breathing bob + blink + chest cycle + pulse.

    The signature is "low energy": small vertical bob (±3 px), a blink
    frame, a chest-light cycle through yellow→blue→green, and an antenna
    pulse at the end.  Every frame is intentionally distinct (no two
    frames share the same pixel content) so GIF optimizers do not merge
    them and the user sees the full 14-frame cycle.

    To guarantee pixel-uniqueness even when two frames share a Y-offset
    we apply a barely-perceptible antenna brightness nudge per frame
    (see :func:`antenna_tint`).  Each factor is in the 0.97–1.03 range
    so the change is invisible at 120x120 display size.
    """
    sub_states = [
        # (kind, shift, antenna_factor)
        ('bob', 0, 1.000),                # 0  rest
        ('bob', -1, 0.985),               # 1  inhale
        ('bob', -2, 1.020),               # 2  hold top
        ('bob', -3, 0.992),               # 3  deeper hold
        ('bob', -2, 1.010),               # 4  partial release
        ('antenna_soft', 0, 1.300),       # 5  antenna pulse (subtle)
        ('blink', 0, 1.000),              # 6  blink (eyes dark)
        ('blink_half', 0, 1.000),         # 7  eyes half-recovered
        ('chest_yellow', 0, 1.000),       # 8  chest yellow bright
        ('chest_blue', 0, 1.000),         # 9  chest blue bright
        ('chest_green', 0, 1.000),        # 10 chest green bright
        ('chest_blue', -1, 0.975),        # 11 chest blue + tiny bob
        ('antenna_strong', -2, 1.600),    # 12 antenna glow + tiny bob
        ('sparkle', -1, 1.005),           # 13 eye sparkle + tiny bob
    ]

    frames: list[Image.Image] = []
    for kind, shift, ant in sub_states:
        if kind == 'bob':
            frame = paste_with_bob(base, shift)
        elif kind == 'antenna_soft':
            frame = antenna_glow(paste_with_bob(base, shift), ant)
        elif kind == 'antenna_strong':
            frame = antenna_glow(paste_with_bob(base, shift), ant)
        elif kind == 'blink':
            frame = blink(paste_with_bob(base, shift))
        elif kind == 'blink_half':
            # Draw a small lighter band across the bottom of each eye
            # so the recovery frame is visually distinct from full base.
            frame = base.copy()
            draw = ImageDraw.Draw(frame)
            band = (5, 10, 25, 220)
            for (x0, y0, x1, y1) in (EYE_LEFT, EYE_RIGHT):
                draw.rectangle(
                    (x0, y0 + (y1 - y0) // 2, x1, y1),
                    fill=band,
                )
            frame = paste_with_bob(frame, shift)
        elif kind == 'chest_yellow':
            frame = chest_cycle(paste_with_bob(base, shift), 'yellow')
        elif kind == 'chest_blue':
            frame = chest_cycle(paste_with_bob(base, shift), 'blue')
        elif kind == 'chest_green':
            frame = chest_cycle(paste_with_bob(base, shift), 'green')
        elif kind == 'sparkle':
            # Tiny sparkles in the eye area (different from happy's sparkles
            # which are paired with all-chest-lights on and a bouncy bob).
            frame = base.copy()
            draw = ImageDraw.Draw(frame)
            for (x0, y0, x1, y1) in (EYE_LEFT, EYE_RIGHT):
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                for dx, dy in ((-4, -4), (4, 4)):
                    sx, sy = cx + dx, cy + dy
                    if y0 < sy < y1 and x0 < sx < x1:
                        draw.rectangle(
                            (sx - 1, sy - 1, sx + 1, sy + 1),
                            fill=(255, 255, 255, 255),
                        )
            frame = paste_with_bob(frame, shift)
        else:  # pragma: no cover - defensive
            frame = paste_with_bob(base, shift)
        # Apply the antenna uniqueness nudge for any frame that does not
        # already call antenna_glow (those frames already change the
        # antenna and are therefore unique on their own).
        if kind not in ('antenna_soft', 'antenna_strong') and ant != 1.0:
            frame = antenna_tint(frame, ant)
        frames.append(frame)
    return frames


def build_busy_frames(base: Image.Image) -> list[Image.Image]:
    """16 frames – rapid chest-light chase + rapid blink + gear orbit.

    Busy signature is "active": chest lights cycle yellow→blue→green twice
    in 16 frames, the eyes blink twice (frames 5 and 12), the antenna
    strobes (frames 3 and 11), and a 3-particle cyan gear orbit rotates
    around the head to make the activity obvious even at 120x120.
    """
    cycle = ['yellow', 'blue', 'green']
    frames: list[Image.Image] = []
    for i in range(BUSY_FRAMES):
        active = cycle[i % 3]
        frame = chest_cycle(base, active, dim_factor=0.25, boost=1.6)
        # 2 quick blinks in the loop
        if i in (5, 12):
            frame = blink(frame)
        # Antenna strobe on 2 beats
        if i in (3, 11):
            frame = antenna_glow(frame, 2.2)
        else:
            frame = antenna_glow(frame, 1.3)
        # Gear orbit overlay
        t = i / BUSY_FRAMES
        frame = add_gear_orbit(frame, t, count=3)
        frames.append(frame)
    return frames


def build_happy_frames(base: Image.Image) -> list[Image.Image]:
    """14 frames – bouncy hop + sparkle eyes + rising particles.

    Happy signature is "celebratory": ±6 px vertical bounce, sparkle eyes
    on every other frame, all three chest lights brightened, and a
    continuous stream of multi-coloured particles rising from the base.
    """
    bounce = [0, -3, -6, -6, -3, 0, 0, 0, 0, -2, -4, -4, -2, 0]
    frames: list[Image.Image] = []
    for i, shift in enumerate(bounce):
        frame = paste_with_bob(base, shift)
        # Sparkle eyes on every other frame
        if i % 2 == 0:
            frame = sparkle_eyes(frame)
        # All chest lights on while bouncing
        if shift < 0:
            frame = all_chest_on(frame, boost=1.5)
        else:
            frame = all_chest_on(frame, boost=1.25)
        # Rising particles
        t = i / HAPPY_FRAMES
        frame = add_rising_particles(frame, t, count=6)
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


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> None:
    base = load_base()

    print(f"\n=== Generating IDLE animation ({IDLE_FRAMES} frames) ===")
    idle_frames = build_idle_frames(base)
    create_sprite_sheet(idle_frames, 'mascot-idle-sprite.png')
    create_gif(idle_frames, 'mascot-idle.gif', duration=250)
    save_individual_frames(idle_frames, 'mascot-idle')

    print(f"\n=== Generating BUSY animation ({BUSY_FRAMES} frames) ===")
    busy_frames = build_busy_frames(base)
    create_sprite_sheet(busy_frames, 'mascot-busy-sprite.png')
    create_gif(busy_frames, 'mascot-busy.gif', duration=140)
    save_individual_frames(busy_frames, 'mascot-busy')

    print(f"\n=== Generating HAPPY animation ({HAPPY_FRAMES} frames) ===")
    happy_frames = build_happy_frames(base)
    create_sprite_sheet(happy_frames, 'mascot-happy-sprite.png')
    create_gif(happy_frames, 'mascot-happy.gif', duration=220)
    save_individual_frames(happy_frames, 'mascot-happy')

    print(f"\n=== Generating ERROR animation ({ERROR_FRAMES} frames) ===")
    error_frames = build_error_frames(base)
    create_sprite_sheet(error_frames, 'mascot-error-sprite.png')
    create_gif(error_frames, 'mascot-error.gif', duration=220)
    save_individual_frames(error_frames, 'mascot-error')

    base.save(os.path.join(str(OUT_DIR), 'mascot-robot-static.png'))
    print("\nDone! Generated frames, sprites, and GIFs in", OUT_DIR)


if __name__ == '__main__':
    main()
