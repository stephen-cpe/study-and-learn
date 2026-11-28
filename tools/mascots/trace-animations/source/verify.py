"""Verify the exported pack: decode every GIF and check frames, timing,
transparency, dimensions, palette and loop settings against manifest.json.

Also checks the neutral first/last frames of one-shots, the held endings of
wake-up/power-down, and the seam of every loop.

Run:  python trace-animations/source/verify.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
PACK = OUT.parent
PALETTE = {tuple(c) for c in json.loads((OUT / "palette.json").read_text())}
NEUTRAL_REF = PACK / "frames" / "idle-blink" / "00.png"


def load_rgba(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def frame_diff(a: Image.Image, b: Image.Image) -> int:
    pa, pb = a.load(), b.load()
    n = 0
    for y in range(a.height):
        for x in range(a.width):
            if pa[x, y] != pb[x, y]:
                n += 1
    return n


def main() -> None:
    manifest = json.loads((PACK / "manifest.json").read_text())
    neutral = load_rgba(NEUTRAL_REF)
    problems: list[str] = []
    print(f"{'animation':22s} {'frames':>6s} {'ms':>6s}  {'loop':5s} "
          f"{'transp':6s} {'palette':7s} {'neutral':7s} {'seam/end':8s}")
    for e in manifest["animations"]:
        name = e["name"]
        gif = PACK / e["gif"]
        issues = []
        if not gif.exists():
            problems.append(f"{name}: missing {gif}")
            continue
        raw = gif.read_bytes()
        has_netscape = b"NETSCAPE2.0" in raw
        im = Image.open(gif)
        sizes = set()
        n = getattr(im, "n_frames", 1)
        durations = []
        transp_ok = True
        palette_ok = True
        neutral_ok = True
        for i in range(n):
            im.seek(i)
            sizes.add(im.size)
            durations.append(im.info.get("duration"))
            rgba = im.convert("RGBA")
            px = rgba.load()
            if px[0, 0][3] != 0 or px[139, 0][3] != 0 or px[0, 139][3] != 0:
                transp_ok = False
            for y in range(0, 140, 3):
                for x in range(0, 140, 3):
                    r, g, b, a = px[x, y]
                    if a and (r, g, b) not in PALETTE:
                        palette_ok = False
            if e["behavior"] == "one-shot" and i in (0, n - 1):
                if name == "wake-up":
                    # starts drooped, must end on neutral
                    if i == n - 1 and frame_diff(rgba, neutral) > 0:
                        neutral_ok = False
                elif name == "power-down":
                    # starts neutral, must end on the held resting pose
                    if i == 0 and frame_diff(rgba, neutral) > 0:
                        neutral_ok = False
                    if i == n - 1 and frame_diff(rgba, neutral) == 0:
                        neutral_ok = False
                elif frame_diff(rgba, neutral) > 0:
                    neutral_ok = False
        # expected values
        if n != e["frame_count"]:
            issues.append(f"frame count {n} != {e['frame_count']}")
        if durations != e["frame_durations_ms"]:
            issues.append(f"durations {durations} != manifest")
        if sizes != {(140, 140)}:
            issues.append(f"size {sizes}")
        if e["loops"] and not has_netscape:
            issues.append("loop GIF lacks NETSCAPE loop ext")
        if not e["loops"] and has_netscape:
            issues.append("one-shot GIF contains NETSCAPE loop ext")
        if sum(durations) != e["total_duration_ms"]:
            issues.append("total duration mismatch")
        if not transp_ok:
            issues.append("background not transparent")
        if not palette_ok:
            issues.append("pixel outside source palette (palette flicker risk)")
        if not neutral_ok:
            issues.append("one-shot does not start/end on neutral")

        # loop seam / one-shot held ending
        im.seek(0)
        first = im.convert("RGBA")
        im.seek(n - 1)
        last = im.convert("RGBA")
        seam = frame_diff(first, last)
        if e["loops"] and seam > 260:
            issues.append(f"loop seam differs by {seam} px")
        end_tag = "held" if e["end_pose"] != "neutral" else f"{seam}px"

        # PNG frames present and matching the GIF
        fdir = PACK / e["frames_dir"]
        pngs = sorted(fdir.glob("*.png"))
        if len(pngs) != e["frame_count"]:
            issues.append(f"png frames {len(pngs)} != {e['frame_count']}")
        else:
            im.seek(n - 1)
            if frame_diff(im.convert("RGBA"), load_rgba(pngs[-1])) > 0:
                issues.append("GIF last frame != PNG last frame")

        status = "OK" if not issues else "FAIL"
        print(f"{name:22s} {n:6d} {sum(durations):6d}  "
              f"{('loop' if e['loops'] else 'once'):5s} "
              f"{('ok' if transp_ok else 'BAD'):6s} "
              f"{('ok' if palette_ok else 'BAD'):7s} "
              f"{('ok' if neutral_ok else 'BAD'):7s} {end_tag:8s} {status}")
        for msg in issues:
            problems.append(f"{name}: {msg}")
            print(f"    - {msg}")

    print()
    if problems:
        print(f"{len(problems)} problems found")
    else:
        print("all checks passed")
    (OUT / "_verify_report.txt").write_text(
        "\n".join(problems) if problems else "all checks passed", encoding="utf-8")


if __name__ == "__main__":
    main()
