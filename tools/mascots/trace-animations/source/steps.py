"""Measure stair-step module along a contour boundary (exact transition x per row)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "trace.png"


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    px = im.load()

    # Left eye: find where "white" begins along each row (left boundary of eye)
    print("left eye white-start x per row:")
    prev = None
    for y in range(300, 500, 1):
        xs = None
        for x in range(330, 620):
            r, g, b, a = px[x, y]
            if a > 200 and r > 200 and g > 200 and b > 200:
                xs = x
                break
        if xs != prev:
            print(f"  y={y:4d}  x={xs}")
            prev = xs

    print("\ncatchlight (pure white inside pupil) extents per row, right pupil:")
    for y in range(300, 380):
        xs = [x for x in range(500, 600)
              if px[x, y][3] > 200 and px[x, y][0] > 245 and px[x, y][1] > 245 and px[x, y][2] > 245]
        if xs:
            print(f"  y={y:4d}  x {min(xs)}..{max(xs)} ({max(xs)-min(xs)+1}px)")

    print("\npupil dark extents per row (right eye), color < 40:")
    for y in range(300, 430, 2):
        xs = [x for x in range(480, 640)
              if px[x, y][3] > 200 and px[x, y][0] < 45 and px[x, y][1] < 45 and px[x, y][2] < 55]
        if xs:
            print(f"  y={y:4d}  x {min(xs)}..{max(xs)} ({max(xs)-min(xs)+1}px)")


if __name__ == "__main__":
    main()
