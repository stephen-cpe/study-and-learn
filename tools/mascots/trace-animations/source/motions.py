"""Trace animation rig: poses, shared motion building blocks, frame compositor.

Everything shared between animations lives here so a motion can be adjusted in
one place:
  * BLINK_STEPS / blink_frames()      - eyelid closing (lid crop over the eye)
  * gaze() / eyes() / brows()         - gaze shifts, whole-eye shifts, brow lifts
  * LED_STATES / led()                - status light colours (source teals)
  * lean() / squash() / hop() / move()- body posture about the anchor
  * NEUTRAL                           - the reassembled source pose (frame 0)

The compositor rebuilds each frame from the layers in source/layers/:
  behind -> eye graphic (lid crop) -> pupil (clipped to the eye) -> brows -> LED,
  then the whole sprite gets the body transform (shear / squash / translate).
All movement is whole-pixel on the working grid.

Run `python trace-animations/source/motions.py` for a neutral-pose rebuild
check against the source extraction.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
LAYERS = OUT / "layers"
CANVAS = 140

# bottom of the outer loop: pivot for leans, nods and squash-and-stretch
ANCHOR_X, ANCHOR_Y = 66, 132

# ---- palette (source palette + LED state tones, all already in the source) --
LED_STATES = {
    "on":    None,               # source pattern: bright cells + darker core
    "bright": (7, 239, 227),     # #07efe3
    "mid":    (3, 159, 144),     # #039f90
    "dim":    (68, 119, 127),    # #44777f
    "off":    (34, 38, 50),      # #222632
}

# shared blink: lid amount (1 = open, 0 = closed) with per-step ms
BLINK_STEPS = [(0.55, 60), (0.0, 70), (0.55, 50)]
SLOW_BLINK_STEPS = [(0.5, 90), (0.0, 150), (0.5, 80)]
DOUBLE_BLINK_STEPS = [(0.55, 50), (0.0, 60), (0.5, 50)]
DOUBLE_BLINK_STEPS_2 = [(0.5, 40), (0.0, 45), (0.5, 35)]


def rint(v: float) -> int:
    return int(math.floor(v + 0.5))


@dataclass(frozen=True)
class Pose:
    """Everything one frame can express.  Offsets are whole cells."""
    lidL: float = 1.0            # 1 = open, 0 = closed (upper lid crop)
    lidR: float = 1.0
    gazeL: tuple = (0, 0)        # pupil offset inside the left eye
    gazeR: tuple = (0, 0)        # pupil offset inside the right eye
    eyeL: tuple = (0, 0)         # whole left-eye offset
    eyeR: tuple = (0, 0)         # whole right-eye offset
    browL: tuple = (0, 0, 0.0)   # left brow  (dx, dy, tilt cells/cell)
    browR: tuple = (0, 0, 0.0)   # right brow (dx, dy, tilt cells/cell)
    led: str = "on"
    shear: float = 0.0           # lean; pivot = anchor (bottom stays planted)
    vscale: float = 1.0          # squash/stretch about the anchor
    hscale: float = 1.0
    dx: int = 0                  # whole-sprite move (hop, recoil)
    dy: int = 0


NEUTRAL = Pose()
POSE_LABELS = {
    "neutral": NEUTRAL,
}


def lids(base: Pose, f: float, both: bool = True, right: float | None = None) -> Pose:
    if both:
        return replace(base, lidL=f, lidR=f if right is None else right)
    return replace(base, lidL=f)


def gaze(base: Pose, L=(0, 0), R=None) -> Pose:
    return replace(base, gazeL=L, gazeR=L if R is None else R)


def eyes(base: Pose, L=(0, 0), R=None) -> Pose:
    return replace(base, eyeL=L, eyeR=L if R is None else R)


def brows(base: Pose, L=(0, 0, 0.0), R=None) -> Pose:
    return replace(base, browL=L, browR=L if R is None else R)


def lean(base: Pose, k: float) -> Pose:
    return replace(base, shear=k)


def squash(base: Pose, f: float, hf: float = 1.0) -> Pose:
    return replace(base, vscale=f, hscale=hf)


def hop(base: Pose, dy: int, f: float = 1.0) -> Pose:
    return replace(base, dy=dy, vscale=f)


def move(base: Pose, dx: int = 0, dy: int = 0) -> Pose:
    return replace(base, dx=dx, dy=dy)


def led(base: Pose, state: str) -> Pose:
    return replace(base, led=state)


def blink_frames(base: Pose = NEUTRAL, steps=BLINK_STEPS) -> list[tuple[Pose, int]]:
    """Shared blink: open -> steps -> open."""
    out = []
    for f, ms in steps:
        out.append((lids(base, f), ms))
    return out


def seq(*chunks) -> list[tuple[Pose, int]]:
    out: list[tuple[Pose, int]] = []
    for c in chunks:
        if isinstance(c, tuple) and len(c) == 2 and isinstance(c[1], int):
            out.append(c)
        else:
            out.extend(c)
    return out


def hold(p: Pose, ms: int) -> list[tuple[Pose, int]]:
    return [(p, ms)]


def lerp_pose(a: Pose, b: Pose, t: float) -> Pose:
    """Blend numeric fields for smooth two-key moves (whole-cell rounding at
    render time)."""
    def lf(x, y):
        if isinstance(x, tuple):
            return tuple(xf + (yf - xf) * t for xf, yf in zip(x, y))
        return x + (y - x) * t
    fields = {}
    for name in a.__dataclass_fields__:
        x, y = getattr(a, name), getattr(b, name)
        if isinstance(x, (int, float)) and name != "led":
            fields[name] = type(x)(lf(x, y)) if not isinstance(x, float) else lf(x, y)
        elif isinstance(x, tuple):
            fields[name] = tuple(type(xf)(lf(xf, yf)) if not isinstance(xf, float) else lf(xf, yf)
                                 for xf, yf in zip(x, y))
        else:
            fields[name] = x if t < 0.5 else y
    return Pose(**fields)


def glide(a: Pose, b: Pose, ms: int, steps: int = 3) -> list[tuple[Pose, int]]:
    """Smooth move from pose a to pose b over ms (whole-cell, few frames)."""
    out = []
    per = max(10, ms // steps // 10 * 10)
    for i in range(1, steps + 1):
        out.append((lerp_pose(a, b, i / steps), per))
    return out


class Rig:
    """Rebuilds frames from the reusable layers."""

    def __init__(self):
        self.meta = json.loads((OUT / "components.json").read_text())
        ox, oy = self.meta["offset"]        # grid -> canvas
        self.layers = {}
        for name in ("behind", "eye_L", "eye_R", "white_L", "white_R",
                     "pupil_L", "pupil_R", "brow_L", "brow_R", "led"):
            self.layers[name] = load_cells(LAYERS / f"{name}.png")
        self.eye_bbox = [[v + (ox if i % 2 == 0 else oy) for i, v in enumerate(b)]
                         for b in (self.meta["eyes"]["L"], self.meta["eyes"]["R"])]
        self.brow_bbox = [[v + (ox if i % 2 == 0 else oy) for i, v in enumerate(b)]
                          for b in (self.meta["brows"]["L"], self.meta["brows"]["R"])]
        # geometry for lid curves (canvas coords)
        self.eye_geom = []
        for b in self.eye_bbox:
            x0, y0, x1, y1 = b
            self.eye_geom.append(((x0 + x1) / 2, (x1 - x0) / 2 or 1, y0, y1))

    # ---- per-part builders -----------------------------------------------
    def _lid_crop(self, cells: dict, i: int, lid: float, shift: tuple) -> dict:
        cx, hw, y0, y1 = self.eye_geom[i]
        if lid >= 1.0:
            return {(x + shift[0], y + shift[1]): c for (x, y), c in cells.items()}
        h = y1 - y0 + 1
        keep = max(2, rint(lid * h))
        base = y1 + 1 - keep
        dipmax = max(0, min(2, keep - 2))
        out = {}
        for (x, y), c in cells.items():
            lx = x - shift[0]
            ly = y - shift[1]
            dxn = (lx - cx) / hw
            cut = base + rint(dipmax * max(0.0, 1.0 - dxn * dxn))
            if ly >= cut:
                out[(x + shift[0], y + shift[1])] = c
        # lid edge: a crisp dark line along the crop boundary
        edge = {}
        for (x, y), c in out.items():
            lx = x - shift[0]
            ly = y - shift[1]
            dxn = (lx - cx) / hw
            cut = base + rint(dipmax * max(0.0, 1.0 - dxn * dxn))
            if ly == cut and c != (21, 21, 31):
                edge[(x, y)] = (21, 21, 31)
        out.update(edge)
        return out

    def render(self, pose: Pose) -> Image.Image:
        cells = dict(self.layers["behind"])
        # whole-pixel movement: interpolated offsets snap to cells here
        shifts = [(rint(pose.eyeL[0]), rint(pose.eyeL[1])),
                  (rint(pose.eyeR[0]), rint(pose.eyeR[1]))]
        gazes = [(rint(pose.gazeL[0]), rint(pose.gazeL[1])),
                 (rint(pose.gazeR[0]), rint(pose.gazeR[1]))]
        lids_v = [pose.lidL, pose.lidR]
        for i, side in enumerate(("L", "R")):
            eye = self._lid_crop(self.layers[f"eye_{side}"], i, lids_v[i], shifts[i])
            white = self._lid_crop(self.layers[f"white_{side}"], i, lids_v[i], shifts[i])
            pup = self._lid_crop(self.layers[f"pupil_{side}"], i, lids_v[i],
                                 (shifts[i][0] + gazes[i][0], shifts[i][1] + gazes[i][1]))
            edge = self._lid_edge(eye, i, lids_v[i], shifts[i])
            mask = set(eye) - edge          # pupil may press into the rim,
            cells.update(white)             # but never above the lid edge
            cells.update(eye)
            for k, c in pup.items():
                if k in mask:
                    cells[k] = c
        for name, bb, tr in (("brow_L", self.brow_bbox[0], pose.browL),
                             ("brow_R", self.brow_bbox[1], pose.browR)):
            bx0, by0, bx1, by1 = bb
            bcx = (bx0 + bx1) / 2
            bdx, bdy, btilt = rint(tr[0]), rint(tr[1]), tr[2]
            for (x, y), c in self.layers[name].items():
                ny = y + bdy + rint(btilt * (x - bcx))
                cells[(x + bdx, ny)] = c
        if pose.led != "on":
            col = LED_STATES[pose.led]
            for k in self.layers["led"]:
                cells[k] = col
        else:
            for k, c in self.layers["led"].items():
                cells[k] = c
        cells = self._body_transform(cells, pose)
        return cells_to_image(cells)

    def _lid_edge(self, eye: dict, i: int, lid: float, shift: tuple) -> set:
        if lid >= 1.0:
            return set()
        cx, hw, y0, y1 = self.eye_geom[i]
        keep = max(2, rint(lid * (y1 - y0 + 1)))
        base = y1 + 1 - keep
        dipmax = max(0, min(2, keep - 2))
        out = set()
        for (x, y) in eye:
            lx = x - shift[0]
            ly = y - shift[1]
            dxn = (lx - cx) / hw
            cut = base + rint(dipmax * max(0.0, 1.0 - dxn * dxn))
            if ly == cut:
                out.add((x, y))
        return out

    def _body_transform(self, cells: dict, pose: Pose) -> dict:
        if pose.shear == 0.0 and pose.vscale == 1.0 and pose.hscale == 1.0 \
                and pose.dx == 0 and pose.dy == 0:
            return cells
        ax, ay = ANCHOR_X, ANCHOR_Y
        rows = defaultdict(dict)
        for (x, y), c in cells.items():
            rows[y][x] = c
        out = {}
        for yp in range(CANVAS):
            y = ay - rint((ay - yp + pose.dy) / pose.vscale)
            if y not in rows:
                continue
            row = rows[y]
            sx = pose.shear * (ay - y)
            for xp in range(CANVAS):
                x = rint((xp - pose.dx - sx - ax) / pose.hscale + ax)
                if x in row:
                    out[(xp, yp)] = row[x]
        return out


def load_cells(path: Path) -> dict:
    im = Image.open(path).convert("RGBA")
    px = im.load()
    return {(x, y): px[x, y][:3]
            for y in range(im.height) for x in range(im.width) if px[x, y][3]}


def cells_to_image(cells: dict) -> Image.Image:
    im = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    px = im.load()
    for (x, y), c in cells.items():
        if 0 <= x < CANVAS and 0 <= y < CANVAS:
            px[x, y] = (*c, 255)
    return im


def _selftest() -> None:
    """Neutral pose must reproduce the source extraction."""
    rig = Rig()
    im = rig.render(NEUTRAL)
    im.resize((CANVAS * 4, CANVAS * 4), Image.NEAREST).save(OUT / "_neutral_check.png")
    src = Image.open(OUT / "grid.png").convert("RGBA")
    ox, oy = rig.meta["offset"]
    diff = 0
    sp, np_ = src.load(), im.load()
    for gy in range(128):
        for gx in range(128):
            a = sp[gx, gy][3] > 0
            b = np_[gx + ox, gy + oy][3] > 0
            if a != b:
                diff += 1
            elif a and sp[gx, gy][:3] != np_[gx + ox, gy + oy][:3]:
                diff += 1
    print(f"neutral rebuild: {diff} differing cells of 128x128 "
          f"({'OK' if diff < 20 else 'CHECK'})  -> _neutral_check.png")


if __name__ == "__main__":
    _selftest()
