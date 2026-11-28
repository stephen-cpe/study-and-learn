"""Print scanline color boundaries to pin down the pixel block size."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    px = im.load()

    def scan_row(y, x0, x1):
        print(f"--- row y={y}  x={x0}..{x1}")
        prev = None
        start = x0
        for x in range(x0, x1 + 1):
            c = px[x, y]
            # coarse signature: alpha bucket + hue bucket
            sig = (c[3] // 64, c[0] // 32, c[1] // 32, c[2] // 32)
            if sig != prev:
                if prev is not None:
                    print(f"  x {start:4d}..{x-1:4d} ({x-start:3d}px)  sample {px[start, y]}")
                prev = sig
                start = x
        print(f"  x {start:4d}..{x1:4d} ({x1-start+1:3d}px)  sample {px[start, y]}")

    def scan_col(x, y0, y1):
        print(f"--- col x={x}  y={y0}..{y1}")
        prev = None
        start = y0
        for y in range(y0, y1 + 1):
            c = px[x, y]
            sig = (c[3] // 64, c[0] // 32, c[1] // 32, c[2] // 32)
            if sig != prev:
                if prev is not None:
                    print(f"  y {start:4d}..{y-1:4d} ({y-start:3d}px)  sample {px[x, start]}")
                prev = sig
                start = y
        print(f"  y {start:4d}..{y1:4d} ({y1-start+1:3d}px)  sample {px[x, start]}")

    # through the pupil's left stair edge and catchlight
    scan_row(350, 420, 620)
    # vertical through catchlight
    scan_col(520, 270, 430)
    # through the collar / LED
    scan_row(680, 700, 860)
    scan_col(780, 590, 760)


if __name__ == "__main__":
    main()
