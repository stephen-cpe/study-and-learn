"""Segment the working grid into reusable layers + the behind-the-eyes fill.

Written to source/layers/ (all at canvas resolution 140x140, transparent):
  body.png      wire + collar with holes where the face parts were
  behind.png    body + the wire continued behind the eye footprints, so any
                eye movement (blink, droop, gaze) reveals plausible pixels
  eye_L/R.png   full eye graphic (white + lavender shade + dark rim)
  white_L/R.png eye white + shade only (fills the eye behind a shifted pupil)
  pupil_L/R.png pupil + cross catchlight (moves inside the white)
  brow_L/R.png  the two independent brow bars
  led.png       the status light (recolourable)

Roles come from the palette and shape topology: the eye white's enclosed holes
are the pupils, the white island inside a pupil is its catchlight, dark islands
above the eyes are the brows, and the bright teal island in the tan collar is
the status light.

Run:  python trace-animations/source/segment.py
"""
from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
LAYERS = OUT / "layers"
LAYERS.mkdir(exist_ok=True)

GRID_N = 128
CANVAS = 140
OX, OY = 8, 4          # grid -> canvas (content lands at x 44..94, y 12..126)

# palette roles (see extract.py / palette.json)
WHITE = {(247, 247, 248), (255, 255, 255), (250, 250, 250)}
SHADE = {(222, 218, 228), (197, 197, 210), (162, 166, 182)}
TEAL_BRIGHT = {(7, 239, 227), (2, 243, 222), (4, 247, 225)}
TAN = {(239, 206, 169), (218, 186, 152), (203, 169, 136), (183, 151, 119),
       (221, 189, 156), (238, 202, 162), (203, 168, 134), (177, 144, 114),
       (91, 68, 58), (83, 75, 67), (59, 51, 52), (104, 83, 73), (93, 69, 59),
       (120, 94, 76), (141, 114, 97)}
GRAY = {(162, 166, 182), (140, 143, 157), (135, 133, 139), (116, 115, 124),
        (92, 91, 102), (98, 97, 105), (128, 129, 144), (112, 115, 132),
        (78, 80, 92), (98, 97, 107)}
DARK = {(21, 21, 31), (21, 21, 30), (34, 38, 50), (34, 39, 52), (65, 64, 79),
        (66, 64, 78), (23, 24, 34), (16, 17, 25), (18, 17, 25), (19, 20, 29)}
STEEL = {(52, 74, 101), (52, 74, 100), (49, 74, 98), (50, 72, 97), (42, 58, 77),
         (42, 55, 73), (63, 93, 112), (64, 94, 115), (64, 89, 113), (89, 107, 132),
         (92, 112, 137), (113, 129, 152), (118, 132, 155)}
TEAL = {(3, 159, 144), (92, 163, 158), (83, 147, 149), (68, 119, 127), (3, 147, 139),
        (84, 148, 149), (73, 127, 133), (64, 109, 121), (70, 106, 123), (13, 94, 85),
        (8, 52, 50), (7, 57, 49)}

DARK_MAIN = (21, 21, 31)          # rim / pupil dark
LED_ZONE = (76, 67, 87, 77)       # protect the status light from despeckling


def load_grid() -> dict:
    im = Image.open(OUT / "grid.png").convert("RGBA")
    px = im.load()
    return {(gx, gy): px[gx, gy][:3]
            for gy in range(GRID_N) for gx in range(GRID_N) if px[gx, gy][3]}


def components(cells: dict, want) -> list[set]:
    seen, comps = set(), []
    for k in cells:
        if k in seen or not want(cells[k]):
            continue
        q = deque([k])
        seen.add(k)
        comp = set()
        while q:
            x, y = q.popleft()
            comp.add((x, y))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n in cells and n not in seen and want(cells[n]):
                        seen.add(n)
                        q.append(n)
        comps.append(comp)
    return comps


def bbox(comp: set):
    xs = [p[0] for p in comp]
    ys = [p[1] for p in comp]
    return min(xs), min(ys), max(xs), max(ys)


def holes_of(shape: set) -> list[set]:
    """4-connected regions of non-shape cells enclosed by the shape."""
    x0, y0, x1, y1 = bbox(shape)
    seen, holes = set(), []
    for gy in range(y0, y1 + 1):
        for gx in range(x0, x1 + 1):
            k = (gx, gy)
            if k in shape or k in seen:
                continue
            q = deque([k])
            seen.add(k)
            comp, edge = set(), False
            while q:
                x, y = q.popleft()
                comp.add((x, y))
                if x in (x0, x1) or y in (y0, y1):
                    edge = True
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (x + dx, y + dy)
                    if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and n not in shape and n not in seen:
                        seen.add(n)
                        q.append(n)
            if not edge:
                holes.append(comp)
    return holes


def despeckle(cells: dict) -> dict:
    """Remove generation-noise specks: tiny components replaced by the locally
    dominant neighbour colour (the status light is protected)."""
    def in_led(k):
        return LED_ZONE[0] <= k[0] <= LED_ZONE[2] and LED_ZONE[1] <= k[1] <= LED_ZONE[3]

    changed = True
    while changed:
        changed = False
        for want, limit in ((lambda c: True, 3), (lambda c: c in TAN, 8)):
            for comp in components(cells, want):
                if len(comp) > limit or all(in_led(k) for k in comp):
                    continue
                neigh = Counter()
                for x, y in comp:
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            n = (x + dx, y + dy)
                            if n not in comp and n in cells:
                                neigh[cells[n]] += 1
                # noise specks along the dark eye/wire rims: prefer the rim dark
                pick = DARK_MAIN if neigh[DARK_MAIN] else (neigh.most_common(1)[0][0] if neigh else None)
                for k in comp:
                    if pick is None:
                        cells.pop(k, None)
                    else:
                        cells[k] = pick
                changed = True
    return cells


def main() -> None:
    cells = despeckle(load_grid())

    is_white = lambda c: c in WHITE
    is_shade = lambda c: c in SHADE
    is_dark = lambda c: c in DARK
    is_tan = lambda c: c in TAN
    is_edgy = lambda c: c in DARK or c in GRAY
    is_tealish = lambda c: c in TEAL_BRIGHT or c in TEAL

    white_comps = sorted(components(cells, is_white), key=len, reverse=True)
    shade_comps = components(cells, is_shade)
    dark_comps = components(cells, is_dark)
    tan_comps = sorted(components(cells, is_tan), key=len, reverse=True)
    led_comps = [c for c in components(cells, is_tealish)
                 if 68 <= bbox(c)[0] and bbox(c)[2] <= 92 and 58 <= bbox(c)[1] and bbox(c)[3] <= 82]

    # ---- roles -----------------------------------------------------------
    eyes = sorted(white_comps[:2], key=lambda s: bbox(s)[0])       # left, right
    eye_set = set().union(*eyes)

    collar, led = set(), set()
    if led_comps:
        seed = set().union(*led_comps)
        sx0, sy0, sx1, sy1 = bbox(seed)
        scx, scy = (sx0 + sx1) // 2, (sy0 + sy1) // 2
        for c in tan_comps:
            x0, y0, x1, y1 = bbox(c)
            if x0 - 4 <= scx <= x1 + 4 and y0 - 4 <= scy <= y1 + 4 and len(c) > 20:
                collar |= c
        if collar:
            cx0, cy0, cx1, cy1 = bbox(collar)
            led = {k for k, c in cells.items() if is_tealish(c)
                   and cx0 - 1 <= k[0] <= cx1 + 1 and cy0 - 1 <= k[1] <= cy1 + 1}

    # lavender shading: hugging an eye belongs to the eyeball, else the wire
    eye_shade = [set(), set()]
    for c in shade_comps:
        for i in range(2):
            if any((x + dx, y + dy) in eyes[i] for x, y in c
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                eye_shade[i] |= c
    all_shade = eye_shade[0] | eye_shade[1]

    # pupils = the eye whites' enclosed holes; catchlight = white island inside
    pupils, catch = [set(), set()], [set(), set()]
    for i, eye in enumerate(eyes):
        for hole in holes_of(eye | eye_shade[i]):
            if len(hole) > 20:
                light = {p for p in hole if is_white(cells[p])}
                pupils[i] |= hole - light
                catch[i] |= light

    # brows = the two dark islands floating above the eyes
    eyes_top = min(bbox(e)[1] for e in eyes)
    brow_list = [c for c in sorted(dark_comps, key=len, reverse=True)
                 if bbox(c)[3] <= eyes_top + 2 and 40 < len(c) < 300 and bbox(c)[0] >= 30][:2]
    brow_list.sort(key=lambda s: bbox(s)[0])
    brows = set().union(*brow_list) if brow_list else set()

    # eye rims = dark/gray cells within 1 cell of the eye shape (bounded so the
    # wire outline that merely touches the eye at the junction stays in body)
    near_eye = set()
    for k in list(eye_set | all_shade):
        x, y = k
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if n in cells and is_edgy(cells[n]):
                    near_eye.add(n)
    all_pupils = pupils[0] | pupils[1]
    all_catch = catch[0] | catch[1]
    rims = near_eye - all_pupils - all_catch - brows

    # per-eye graphics.  sclera = white + shade + the pupil footprint filled
    # white ("fill the eye white behind a shifted pupil"); the eye graphic adds
    # the rim and is self-contained for blinks and gaze shifts.
    eye_gfx, eye_white, rims_i = [], [], []
    for i in range(2):
        x0, y0, x1, y1 = bbox(eyes[i])
        rim = {k for k in rims if x0 - 2 <= k[0] <= x1 + 2 and y0 - 2 <= k[1] <= y1 + 2}
        other = eyes[1 - i]
        ox0, oy0, ox1, oy1 = bbox(other)
        # the shared rim between the eyes belongs to the nearer eye only
        rim = {k for k in rim if not (
            ox0 - 1 <= k[0] <= ox1 + 1 and oy0 - 1 <= k[1] <= oy1 + 1
            and abs(k[0] - (x0 + x1) / 2) > abs(k[0] - (ox0 + ox1) / 2))}
        rims_i.append(rim)
        sc = {k for k in (eyes[i] | eye_shade[i] | pupils[i] | catch[i])
              if x0 - 1 <= k[0] <= x1 + 1 and y0 - 1 <= k[1] <= y1 + 1}
        eye_white.append(sc)
        eye_gfx.append(sc | rim)

    claimed = set().union(*eye_gfx, all_pupils, all_catch, brows, led)
    body = {k: cells[k] for k in cells if k not in claimed}

    # ---- behind the eyes: continue the wire vertically through each -------
    # footprint (per-column copy from the nearest visible row above, else
    # below).  Only cells a face part can vacate are filled, so real gaps in
    # the silhouette stay transparent.
    behind = dict(body)
    reveal = set().union(*eye_gfx, all_pupils, all_catch, brows)
    REACH = 4          # the wire only tucks a few cells behind a rim

    def band_src(x, y, up_to, down_to):
        """Colour of the wire band that runs directly behind (x, y): follow the
        column through face cells; if a body cell sits within REACH on the far
        side the band continues behind here, otherwise nothing does (a gap)."""
        yy = y - 1
        while yy >= up_to and (x, yy) in reveal:
            yy -= 1
        if yy >= up_to and (x, yy) in body and y - yy <= REACH:
            return cells[(x, yy)]
        yy = y + 1
        while yy < down_to and (x, yy) in reveal:
            yy += 1
        if yy < down_to and (x, yy) in body and yy - y <= REACH:
            return cells[(x, yy)]
        return None

    for g in eye_gfx:
        x0, y0, x1, y1 = bbox(g)
        for y in range(y0 - 1, y1 + 2):
            for x in range(x0 - 1, x1 + 2):
                if (x, y) not in reveal or (x, y) in body:
                    continue
                src = band_src(x, y, y0 - 12, y1 + 12)
                if src is not None:
                    behind[(x, y)] = src
    for b in brow_list:
        bx0, by0, bx1, by1 = bbox(b)
        for y in range(by0, by1 + 1):
            for x in range(bx0, bx1 + 1):
                if (x, y) not in reveal or (x, y) in behind:
                    continue
                src = band_src(x, y, max(0, by0 - 8), by1 + 8)
                if src is not None:
                    behind[(x, y)] = src

    # ---- render layers ----------------------------------------------------
    def canvas_img(paint: dict) -> Image.Image:
        im = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        px = im.load()
        for (gx, gy), c in paint.items():
            px[gx + OX, gy + OY] = (*c, 255)
        return im

    def subset(*sets_) -> dict:
        out = {}
        for s in sets_:
            for k in s:
                out[k] = cells[k]
        return out

    WHITE_FILL = (247, 247, 248)

    def eye_paint(sclera: set, rim: set) -> dict:
        out = {}
        for k in sclera:                       # pupil footprint filled white
            out[k] = WHITE_FILL if k in pupils[0] or k in pupils[1] else cells[k]
        for k in rim:
            out[k] = cells[k]
        return out

    images = {
        "body": canvas_img(body),
        "behind": canvas_img(behind),
        "eye_L": canvas_img(eye_paint(eye_white[0], rims_i[0])),
        "eye_R": canvas_img(eye_paint(eye_white[1], rims_i[1])),
        "white_L": canvas_img(eye_paint(eye_white[0], set())),
        "white_R": canvas_img(eye_paint(eye_white[1], set())),
        "pupil_L": canvas_img(subset(pupils[0] | catch[0])),
        "pupil_R": canvas_img(subset(pupils[1] | catch[1])),
        "brow_L": canvas_img(subset(brow_list[0]) if brow_list else set()),
        "brow_R": canvas_img(subset(brow_list[1]) if len(brow_list) > 1 else set()),
        "led": canvas_img(subset(led)),
    }
    for name, im in images.items():
        im.save(LAYERS / f"{name}.png")
        im.resize((CANVAS * 4, CANVAS * 4), Image.NEAREST).save(LAYERS / f"{name}_4x.png")

    # role debug map on the grid
    rolemap = Image.new("RGBA", (GRID_N, GRID_N), (0, 0, 0, 0))
    rp = rolemap.load()
    def fill(s, col):
        for k in s:
            rp[k] = (*col, 255)
    fill(body, (80, 110, 150))
    fill(eye_set | all_shade, (240, 240, 245))
    fill(rims, (120, 120, 140))
    fill(all_pupils, (30, 30, 45))
    fill(all_catch, (255, 255, 0))
    fill(brows, (255, 120, 0))
    fill(led, (0, 255, 180))
    rolemap.resize((GRID_N * 4, GRID_N * 4), Image.NEAREST).save(OUT / "roles.png")

    meta = {
        "grid": GRID_N, "canvas": CANVAS, "offset": [OX, OY],
        "anchor": [66, 132],   # bottom of the outer loop (canvas coords)
        "eyes": {"L": list(bbox(eye_gfx[0])), "R": list(bbox(eye_gfx[1]))},
        "whites": {"L": list(bbox(eye_white[0])), "R": list(bbox(eye_white[1]))},
        "pupils": {"L": list(bbox(pupils[0])), "R": list(bbox(pupils[1]))},
        "catch": {"L": list(bbox(catch[0])), "R": list(bbox(catch[1]))},
        "brows": {"L": list(bbox(brow_list[0])), "R": list(bbox(brow_list[1]))},
        "led": list(bbox(led)) if led else None,
        "collar": list(bbox(collar)) if collar else None,
        "content_bbox": [36, 8, 86, 122],
    }
    with open(OUT / "components.json", "w") as f:
        json.dump(meta, f, indent=2)

    for label, s in (("body", body), ("eyes", set().union(*eye_gfx)),
                     ("pupils", all_pupils), ("catch", all_catch),
                     ("brows", brows), ("led", led)):
        print(f"{label:7s} {len(s) if not isinstance(s, dict) else len(s)}")
    print("eye L gfx", bbox(eye_gfx[0]), "white", bbox(eye_white[0]))
    print("eye R gfx", bbox(eye_gfx[1]), "white", bbox(eye_white[1]))
    print("wrote layers/*.png, roles.png, components.json")


if __name__ == "__main__":
    main()
