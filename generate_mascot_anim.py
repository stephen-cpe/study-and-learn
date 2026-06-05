#!/usr/bin/env python3
"""
Generate animated mascot frames and sprite sheets for the Study Robot.
Uses the original mascot-robot.png as exact base reference.
Creates variants for idle animation, processing, and happy states.

Cross-platform: resolves paths relative to this script's location, so the
script works identically on Windows 11 (dev) and Ubuntu/Linux (prod).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance
import numpy as np
import os

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_PATH = SCRIPT_DIR / 'src' / 'static' / 'images' / 'mascot-robot.png'
OUT_DIR = SCRIPT_DIR / 'src' / 'static' / 'images'
os.makedirs(OUT_DIR, exist_ok=True)

def load_base():
    img = Image.open(str(BASE_PATH)).convert('RGBA')
    print(f"Loaded base: {img.size}")
    return img

def get_eye_bboxes():
    # Hardcoded from analysis: left and right eyes
    left = (305, 290, 360, 357)  # x0,y0,x1,y1
    right = (453, 289, 505, 357)
    return left, right

def get_chest_lights():
    # (name, bbox)
    yellow = (360, 475, 378, 490)
    blue = (394, 475, 413, 490)
    green = (425, 444, 444, 491)  # note slight wider
    return [
        ('yellow', yellow),
        ('blue', blue),
        ('green', green)
    ]

def get_antenna_ball():
    # Top antenna light ball approx
    return (348, 70, 417, 119)

def create_blink_frame(base):
    """Eyes powered off / blink: fill eye areas with dark display color"""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    left, right = get_eye_bboxes()
    dark_color = (5, 10, 25, 255)  # very dark blue-black for "off" screen
    draw.rectangle(left, fill=dark_color)
    draw.rectangle(right, fill=dark_color)
    return img

def create_antenna_glow_frame(base, factor=1.6):
    """Brighten the antenna top ball"""
    img = base.copy()
    arr = np.array(img)
    x0, y0, x1, y1 = get_antenna_ball()
    # Brighten the blue in that region
    region = arr[y0:y1, x0:x1]
    # Only affect blue-ish pixels
    mask = (region[:,:,2] > 100) & (region[:,:,0] < 100) & (region[:,:,1] < 150) & (region[:,:,3] > 200)
    for c in range(3):
        region[:,:,c][mask] = np.clip(region[:,:,c][mask].astype(int) * factor, 0, 255).astype(np.uint8)
    # Make top brighter
    arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)

def create_chest_cycle_frame(base, active_light='yellow', dim_factor=0.4):
    """Cycle chest lights: one bright, others dimmed"""
    img = base.copy()
    arr = np.array(img)
    lights = get_chest_lights()
    for name, bbox in lights:
        x0,y0,x1,y1 = bbox
        region = arr[y0:y1, x0:x1]
        if name == active_light:
            # Brighten it
            region = np.clip(region.astype(int) * 1.3, 0, 255).astype(np.uint8)
        else:
            # Dim it
            region = np.clip(region.astype(int) * dim_factor, 0, 255).astype(np.uint8)
        arr[y0:y1, x0:x1] = region
    return Image.fromarray(arr)

def create_happy_frame(base):
    """Happy expression: brighter eyes, slight sparkle"""
    img = base.copy()
    arr = np.array(img)
    left, right = get_eye_bboxes()
    # Brighten the green eyes
    for bbox in [left, right]:
        x0,y0,x1,y1 = bbox
        region = arr[y0:y1, x0:x1]
        # Brighten green channel more
        g = region[:,:,1].astype(int)
        region[:,:,1] = np.clip(g * 1.4, 0, 255).astype(np.uint8)
        # Add some sparkle whites in corners or center
        # Add small white dots
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        for dx, dy in [(-5,-5), (5,-5), (-5,5), (5,5), (0,0)]:
            sx, sy = cx + dx, cy + dy
            if y0 < sy < y1 and x0 < sx < x1:
                arr[sy, sx] = (255, 255, 255, 255)
    return Image.fromarray(arr)

def create_bob_frame(base, shift=3):
    """Slight vertical bob: shift content down a bit"""
    img = Image.new('RGBA', base.size, (0,0,0,0))
    # Paste base shifted down
    img.paste(base, (0, shift), base)
    # To avoid clipping top, perhaps also shift some parts, but for simple, ok. 
    # Since transparent, the top will have gap, but for small shift ok as it bobs.
    return img

def create_sprite_sheet(frames, filename, frame_width=None):
    """Create horizontal sprite sheet from list of frames"""
    if not frames:
        return
    w, h = frames[0].size
    total_w = w * len(frames)
    sheet = Image.new('RGBA', (total_w, h), (0,0,0,0))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (i * w, 0), frame)
    out_path = os.path.join(str(OUT_DIR), filename)
    sheet.save(out_path, "PNG")
    print(f"Saved sprite sheet: {out_path} ({len(frames)} frames, size {sheet.size})")
    return out_path

def _prepare_frame_for_gif(frame):
    """Convert an RGBA frame to a P-mode frame with a transparent background.

    Why this is non-trivial:
      After ``quantize()``, Pillow's adaptive palette does NOT guarantee that
      palette index 0 will be the most common color (the background).  In our
      mascot PNG the background is black, but quantize put black at index 255.
      Saving with ``transparency=0`` would then make some near-white palette
      entry transparent while the actual background pixels stay opaque.

    The reliable approach:
      1. Quantize the RGBA image directly to a 255-color palette.  This
         leaves palette index 255 unused.
      2. Build the alpha mask from the source frame (255 where alpha < 128).
      3. ``paste(255, mask=mask)`` writes palette index 255 at every
         originally-transparent location.  The palette at index 255 is
         whatever Pillow padded with — the visual color does not matter
         because the GIF renderer will treat this index as transparent.
      4. Save with ``transparency=255`` and ``disposal=2`` so each frame
         clears to the background before the next is drawn.

    NOTE: GIF only supports 1-bit (binary) transparency, so anti-aliased
    edges will appear slightly more pixelated than the source PNG.  This
    is an inherent limitation of the format.
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


def create_gif(frames, filename, duration=200):
    """Create animated GIF from list of frames with transparency preserved."""
    out_path = os.path.join(str(OUT_DIR), filename)
    prepared = [_prepare_frame_for_gif(f) for f in frames]
    prepared[0].save(
        out_path,
        save_all=True,
        append_images=prepared[1:],
        duration=duration,
        loop=0,
        transparency=255,
        disposal=2
    )
    print(f"Saved GIF: {out_path}")
    return out_path

def main():
    base = load_base()
    
    # === IDLE ANIMATION (4 frames cycle) ===
    print("\n=== Generating IDLE frames ===")
    idle_frames = []
    idle_frames.append(base.copy())  # frame 0: base
    idle_frames.append(create_blink_frame(base))  # frame 1: blink
    idle_frames.append(create_antenna_glow_frame(base))  # frame 2: antenna glow
    idle_frames.append(create_chest_cycle_frame(base, 'yellow'))  # frame 3: chest cycle
    # Add a bob or another
    idle_frames.append(create_bob_frame(base, shift=2))  # but we'll use 4
    
    # Trim to 4 nice ones
    idle_frames = [
        base.copy(),
        create_blink_frame(base),
        create_antenna_glow_frame(base, 1.8),
        create_chest_cycle_frame(base, 'blue')
    ]
    
    create_sprite_sheet(idle_frames, 'mascot-idle-sprite.png')
    create_gif(idle_frames, 'mascot-idle.gif', duration=300)
    
    # === BUSY / PROCESSING ANIMATION (more active) ===
    print("\n=== Generating BUSY frames ===")
    busy_frames = []
    # Cycle through lights + blink occasionally
    busy_frames.append(create_chest_cycle_frame(base, 'yellow', dim_factor=0.3))
    busy_frames.append(create_chest_cycle_frame(base, 'blue', dim_factor=0.3))
    busy_frames.append(create_chest_cycle_frame(base, 'green', dim_factor=0.3))
    busy_frames.append(create_blink_frame(base))  # blink during busy
    busy_frames.append(create_antenna_glow_frame(base, 2.0))
    busy_frames.append(create_chest_cycle_frame(base, 'yellow', dim_factor=0.3))
    
    create_sprite_sheet(busy_frames, 'mascot-busy-sprite.png')
    create_gif(busy_frames, 'mascot-busy.gif', duration=150)  # faster for busy
    
    # === HAPPY / COMPLETE ===
    print("\n=== Generating HAPPY frames ===")
    happy_frames = []
    happy_frames.append(create_happy_frame(base))
    happy_frames.append(base.copy())
    happy_frames.append(create_happy_frame(base))
    happy_frames.append(create_antenna_glow_frame(base, 1.5))
    happy_frames.append(create_chest_cycle_frame(base, 'green', dim_factor=0.5))  # all happy lights
    
    create_sprite_sheet(happy_frames, 'mascot-happy-sprite.png')
    create_gif(happy_frames, 'mascot-happy.gif', duration=250)
    
    # Also save individual frames for reference or alternative use
    for i, f in enumerate(idle_frames):
        f.save(os.path.join(OUT_DIR, f'mascot-idle-frame{i}.png'))
    for i, f in enumerate(busy_frames):
        f.save(os.path.join(OUT_DIR, f'mascot-busy-frame{i}.png'))
    for i, f in enumerate(happy_frames):
        f.save(os.path.join(OUT_DIR, f'mascot-happy-frame{i}.png'))
    
    print("\n=== Also saving base as mascot-robot.png (original) ===")
    # Already copied
    
    # Create a single static for fallback
    base.save(os.path.join(OUT_DIR, 'mascot-robot-static.png'))
    
    print("\nDone! Generated frames and sprites in", OUT_DIR)

if __name__ == '__main__':
    main()
