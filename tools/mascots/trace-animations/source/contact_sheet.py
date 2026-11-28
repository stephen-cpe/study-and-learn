"""Contact sheets for judging motion at display sizes (48 px / 96 px) and for
checking pixels at 4x.

Run:  python trace-animations/source/contact_sheet.py idle-blink celebrate ...
      python trace-animations/source/contact_sheet.py            (all)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
PACK = OUT.parent
FRAMES = PACK / "frames"


def sheet(name: str) -> None:
    fdir = FRAMES / name
    files = sorted(fdir.glob("*.png"))
    frames = [Image.open(f).convert("RGBA") for f in files]
    n = len(frames)
    pad = 8
    row4x = 140 * 2 + 4
    w = pad + n * (row4x + pad)
    h = pad + row4x + 12 + 96 + 12 + 48 + 20
    im = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    mid = w // 2
    d.rectangle([mid, 0, w, h], fill=(24, 26, 34, 255))   # dark half background
    y = pad
    for i, f in enumerate(frames):
        x = pad + i * (row4x + pad)
        im.alpha_composite(f.resize((row4x, row4x), Image.NEAREST), (x, y))
    y = pad + row4x + 12
    for i, f in enumerate(frames):
        x = pad + i * (row4x + pad) + (row4x - 96) // 2
        im.alpha_composite(f.resize((96, 96), Image.NEAREST), (x, y))
    y = pad + row4x + 12 + 96 + 12
    for i, f in enumerate(frames):
        x = pad + i * (row4x + pad) + (row4x - 48) // 2
        im.alpha_composite(f.resize((48, 48), Image.NEAREST), (x, y))
    d.text((pad, h - 14), f"{name}  ({n} frames)  top: 2x pixel view   middle: 96px   "
                          f"bottom: 48px   left half light bg / right half dark bg",
           fill=(90, 90, 90, 255))
    out = OUT / "_sheets"
    out.mkdir(exist_ok=True)
    im.save(out / f"{name}.png")

    # compact sheet: display sizes only (no 4x row) - what the eye actually sees
    w2 = pad + n * (96 + pad)
    h2 = pad + 96 + 12 + 48 + 18
    im2 = Image.new("RGBA", (w2, h2), (255, 255, 255, 255))
    d2 = ImageDraw.Draw(im2)
    d2.rectangle([w2 // 2, 0, w2, h2], fill=(24, 26, 34, 255))
    for i, f in enumerate(frames):
        im2.alpha_composite(f.resize((96, 96), Image.NEAREST), (pad + i * (96 + pad), pad))
        im2.alpha_composite(f.resize((48, 48), Image.NEAREST), (pad + i * (96 + pad) + 24, pad + 108))
    d2.text((pad, h2 - 13), f"{name}: 96px row / 48px row", fill=(90, 90, 90, 255))
    im2.save(out / f"{name}_sizes.png")
    print(f"wrote _sheets/{name}.png, _sheets/{name}_sizes.png")


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.name for p in FRAMES.iterdir() if p.is_dir())
    for nm in names:
        sheet(nm)
