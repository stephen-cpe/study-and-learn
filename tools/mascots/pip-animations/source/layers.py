"""Build Pip's editable layer set from pip.png.

Run:  python layers.py
Writes:
  layers/base.png        cleaned working-grid sprite (quantized pip.png)
  layers/body.png        torso, belly, legs, feet, neck + gray bolt, arm sockets
  layers/head.png        head + snout + faceplate + cheek + nostrils + mouth corner
  layers/tail.png        upturned tail (root overlaps the hip so it stays connected)
  layers/arm_near.png    screen-left forearm (the visible one)
  layers/arm_far.png     screen-right forearm
  layers/eyeL_mint.png, eyeR_mint.png     mint eye shapes (plus shapes)
  layers/eyeL_pupil.png, eyeR_pupil.png   square pupil + attached catchlight
  layers/lidL.png, lidR.png               short mint lid marks
  layers/mouth_C.png / mouth_R.png / mouth_S.png   mouth shapes (closed/rest/slightly open)
  _diag/roles.png, _diag/neutral_check.png

The neutral reassembly is compared against the quantized source before any
animation is rendered.
"""
import os, json, sys
import numpy as np
from PIL import Image, ImageDraw

import riglib
from riglib import RIG, PAL, CLASSES, RGBA, CW, CH, CELL, ORIGIN

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, RIG["source_png"]))
LAY = os.path.join(HERE, "layers")
DIAG = os.path.join(HERE, "_diag")
os.makedirs(LAY, exist_ok=True)
os.makedirs(DIAG, exist_ok=True)

CLASS_IDX = {c: i for i, c in enumerate(CLASSES)}
IDX_CLASS = {i: c for c, i in CLASS_IDX.items()}
CENTERS = np.array([PAL[c] for c in CLASSES], float)

# ---------------------------------------------------------------- tooth table
# Clean rebuilt tooth unit (rig.json "tooth_unit" rect = x63..75, y92..98).
# '#' outline_dark, 'I' ivory, 'd' blue_deep, 'B' blue_mid.  Rows 92..98.
TOOTH_ROWS = {
    92: "###IIIIII####",
    93: "###IIIIII###d",
    94: "d##IIIIII###d",
    95: "d##IIIIII###d",
    96: "d##IIIIII###d",
    97: "d##IIIIII###d",
    98: "dddBBBBBBBddB",
}
CHAR_CLASS = {"#": "outline_dark", "I": "ivory", "d": "blue_deep",
              "B": "blue_mid", "b": "blue_shade", "P": "blue_pale",
              "L": "blue_light", "M": "mint", "O": "orange", "W": "white",
              "G": "gray", "@": "plate_dark", ".": None}

def rect_cells(r):
    x0, y0, x1, y1 = r
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]

# ---------------------------------------------------------------- build grid
def build_grid():
    im = Image.open(SRC).convert("RGBA")
    arr = np.array(im).astype(float)
    H, W = arr.shape[:2]
    nx0, ny0 = ORIGIN
    gray_zone = tuple(RIG["cuts"].get("gray_zone", [45, 108, 51, 115]))
    labels = np.zeros((CH, CW), object)
    for cy in range(CH):
        y0 = ny0 + cy * CELL
        for cx in range(CW):
            x0 = nx0 + cx * CELL
            blk = arr[max(0, y0):y0 + CELL, max(0, x0):x0 + CELL]
            if blk.size == 0:
                labels[cy, cx] = None
                continue
            a = blk[..., 3]
            m = a > 128
            if not m.any():
                labels[cy, cx] = None
                continue
            px = blk[..., :3][m]
            allow_gray = (gray_zone[0] <= cx <= gray_zone[2] and
                          gray_zone[1] <= cy <= gray_zone[3])
            cent = CENTERS if allow_gray else CENTERS[[i for i, c in enumerate(CLASSES) if c != "gray"]]
            names = CLASSES if allow_gray else [c for c in CLASSES if c != "gray"]
            d = ((px[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
            votes = d.argmin(axis=1)
            counts = np.bincount(votes, minlength=len(names))
            labels[cy, cx] = names[int(counts.argmax())]

    # one majority pass among opaque neighbours to de-speckle gradients
    out = labels.copy()
    for cy in range(CH):
        for cx in range(CW):
            c = labels[cy, cx]
            if c is None:
                continue
            neigh = []
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < CH and 0 <= nx < CW and labels[ny, nx] is not None:
                        neigh.append(labels[ny, nx])
            cnt = {}
            for n in neigh:
                cnt[n] = cnt.get(n, 0) + 1
            best = max(cnt, key=cnt.get)
            if best != c and cnt[best] >= 5:
                out[cy, cx] = best
    return out

def grid_to_img(labels):
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    px = img.load()
    for cy in range(CH):
        for cx in range(CW):
            c = labels[cy, cx]
            if c is not None:
                px[cx, cy] = RGBA[c]
    return img

def blank():
    return Image.new("RGBA", (CW, CH), (0, 0, 0, 0))

def cut(labels, cells, fill_rects=None, fill_color=None):
    """Layer image with the given cells copied from the grid."""
    img = blank()
    px = img.load()
    src = grid_to_img(labels).load()
    for x, y in cells:
        if 0 <= x < CW and 0 <= y < CH and labels[y][x] is not None:
            px[x, y] = src[x, y]
    if fill_rects:
        d = ImageDraw.Draw(img)
        for r in fill_rects:
            d.rectangle(r, fill=fill_color)
    return img

# ---------------------------------------------------------------- part masks
def part_cells(labels):
    cuts = RIG["cuts"]
    sx = cuts["head_split_x"]
    ox0, ox1 = cuts["jaw_overhang_x"]
    sy = cuts["head_split_y"]
    jy = cuts["jaw_overhang_y"]
    bounds = {int(k): v for k, v in cuts["tail_left_by_row"].items()}
    tr0, tr1 = cuts["tail_rows"]
    rr0, rr1 = cuts["tail_root_rows"]
    rx0, rx1 = cuts["tail_root_x"]
    an = cuts["arm_near_rect"]
    af = cuts["arm_far_rect"]
    root_rows = cuts["arm_root_rows"]
    pale = "blue_pale"

    def in_rect(r, x, y):
        return r[0] <= x <= r[2] and r[1] <= y <= r[3]

    def in_arm_root(y):
        return any(a <= y <= b for a, b in root_rows)

    def tail_xmin(y):
        xmin = None
        for k in sorted(bounds):
            if y >= k:
                xmin = bounds[k]
        return xmin

    head, tail, arm_near, arm_far, body = [], [], [], [], []
    for y in range(CH):
        for x in range(CW):
            cls = labels[y][x]
            if cls is None:
                continue
            if y < sy or (y < jy and ox0 <= x <= ox1):
                head.append((x, y))
                continue
            if tr0 <= y <= tr1 and cls != pale:
                if y >= rr0:
                    if rx0 <= x <= rx1 and cls != "outline_dark":
                        tail.append((x, y))
                        body.append((x, y))      # shared tail-root silhouette
                        continue
                elif x >= tail_xmin(y):
                    tail.append((x, y))          # swinging band
                    continue
            if in_rect(an, x, y):
                arm_near.append((x, y))
                if in_arm_root(y):
                    body.append((x, y))          # socket rows stay behind the arm
                continue
            if in_rect(af, x, y):
                arm_far.append((x, y))
                if in_arm_root(y):
                    body.append((x, y))
                continue
            body.append((x, y))
    return head, tail, arm_near, arm_far, body

# ---------------------------------------------------------------- procedural
def mint_img(side):
    img = blank()
    d = ImageDraw.Draw(img)
    for r in RIG["eyes"][side]["mint_rects"]:
        d.rectangle(r, fill=RGBA["mint"])
    return img

def pupil_img(side):
    e = RIG["eyes"][side]
    img = blank()
    d = ImageDraw.Draw(img)
    d.rectangle(e["pupil"], fill=RGBA["plate_dark"])
    d.rectangle(e["catch"], fill=RGBA["white"])
    return img

def lid_img(side):
    e = RIG["eyes"][side]
    img = blank()
    d = ImageDraw.Draw(img)
    x0, x1 = e["lid_span"]
    y0, y1 = e["lid_row"]
    d.rectangle([x0, y0, x1, y1], fill=RGBA["mint"])
    return img

def mouth_img(kind):
    m = RIG["mouth"]
    x0, y0, x1, y1 = m["zone_b"][0], m["zone_b"][1], m["zone_b"][2], m["zone_b"][3]
    img = blank()
    d = ImageDraw.Draw(img)
    d.rectangle([x0, y0, x1, y1], fill=RGBA["blue_mid"])
    # row 89: mouth corner continues left of x59, shade right of it
    ax0, ay0, ax1, ay1 = m["zone_a"]
    d.rectangle([ax0, y0, 58, y0], fill=RGBA["outline_dark"])
    d.rectangle([59, y0, x1, y0], fill=RGBA["blue_deep"])
    h = m["opening_rows"][kind]
    d.rectangle([ax0, 90, x1, 90 + h - 1], fill=RGBA["outline_dark"])
    shade = 90 + h
    d.rectangle([ax0, shade, 62, shade], fill=RGBA["blue_deep"])
    d.rectangle([76, shade, x1, shade], fill=RGBA["blue_deep"])
    tx0, ty0, tx1, ty1 = m["tooth_unit"]
    for ty in range(ty0, ty1 + 1):
        row = TOOTH_ROWS[ty]
        for i, ch in enumerate(row):
            cls = CHAR_CLASS[ch]
            if cls:
                img.putpixel((tx0 + i, ty), RGBA[cls])
    return img

# ---------------------------------------------------------------- head poses
def build_head_poses(head):
    """Bake the reusable head poses as editable layer variants."""
    zones = [tuple(z) for z in RIG["head_pose_zones"]]
    for name, hp in RIG["head_poses"].items():
        img = head
        if hp.get("snout_squeeze"):
            img = riglib.squeeze_cols(img, hp["snout_x0"], hp["snout_squeeze"])
        if hp.get("zone_shift"):
            img = riglib.shift_zones(img, zones, hp["zone_shift"])
        if img is not head:
            img.save(os.path.join(LAY, "head_%s.png" % name))
            print("  head pose layer: head_%s.png (%s)" % (name, hp.get("label", name)))

# ---------------------------------------------------------------- main
def main():
    labels = build_grid()
    base = grid_to_img(labels)
    base.save(os.path.join(LAY, "base.png"))

    head_c, tail_c, an_cells, af_cells, body_c = part_cells(labels)

    # head: eye bboxes are the preserved dark faceplate; features ride the head
    head = cut(labels, head_c)
    d = ImageDraw.Draw(head)
    for side in ("L", "R"):
        d.rectangle(RIG["eyes"][side]["bbox"], fill=RGBA["outline_dark"])

    body = cut(labels, body_c)
    d = ImageDraw.Draw(body)
    for r in RIG["cuts"]["neck_filler_rects"]:
        d.rectangle(r, fill=RGBA["outline_dark"])

    tail = cut(labels, tail_c)
    arm_near = cut(labels, an_cells)
    arm_far = cut(labels, af_cells)

    imgs = {
        "head": head, "body": body, "tail": tail,
        "arm_near": arm_near, "arm_far": arm_far,
        "eyeL_mint": mint_img("L"), "eyeR_mint": mint_img("R"),
        "eyeL_pupil": pupil_img("L"), "eyeR_pupil": pupil_img("R"),
        "lidL": lid_img("L"), "lidR": lid_img("R"),
        "mouth_C": mouth_img("C"), "mouth_R": mouth_img("R"), "mouth_S": mouth_img("S"),
    }
    for name, img in imgs.items():
        img.save(os.path.join(LAY, name + ".png"))
    build_head_poses(head)

    # ---- roles map
    ROLE_COLORS = {
        "head": (255, 90, 90), "body": (90, 160, 255), "tail": (255, 200, 60),
        "arm_near": (200, 110, 255), "arm_far": (150, 90, 220),
    }
    roles = Image.new("RGB", (CW, CH), (20, 20, 20))
    d = ImageDraw.Draw(roles)
    def paint(cells, col):
        for x, y in cells:
            roles.putpixel((x, y), col)
    paint(tail_c, ROLE_COLORS["tail"])
    paint(body_c, ROLE_COLORS["body"])
    paint(af_cells, ROLE_COLORS["arm_far"])
    paint(an_cells, ROLE_COLORS["arm_near"])
    paint(head_c, ROLE_COLORS["head"])
    for side in ("L", "R"):
        paint(rect_cells(RIG["eyes"][side]["bbox"]), (120, 255, 170))
    paint(rect_cells(RIG["mouth"]["zone_a"]) + rect_cells(RIG["mouth"]["zone_b"]), (255, 120, 60))
    roles.resize((CW * 4, CH * 4), Image.NEAREST).save(os.path.join(DIAG, "roles.png"))

    # ---- neutral reassembly vs quantized source
    import riglib as R
    neutral = R.compose(R.pose())
    nb = np.array(neutral)
    bb = np.array(base)
    diff = (nb != bb).any(axis=2)
    ys, xs = np.nonzero(diff)
    print(f"neutral vs quantized source: {diff.sum()} differing cells of {CW*CH}")
    if diff.sum():
        buckets = {}
        for x, y in zip(xs, ys):
            buckets.setdefault(y // 24 * 1000 + x // 24, []).append((x, y))
        worst = sorted(buckets.items(), key=lambda kv: -len(kv[1]))[:8]
        for k, v in worst:
            x, y = v[0]
            print(f"   cluster near ({x},{y}): {len(v)} cells")

    # side-by-side: original pip.png | quantized grid | reassembly | diff
    zoom = 2
    panel_w, panel_h = CW * zoom, CH * zoom
    src_im = Image.open(SRC).convert("RGBA")
    nx0, ny0 = ORIGIN
    src_crop = src_im.crop((nx0, ny0, nx0 + CW * CELL, ny0 + CH * CELL))
    src_small = src_crop.resize((CW, CH), Image.BOX).resize((panel_w, panel_h), Image.NEAREST)
    sheet = Image.new("RGB", (panel_w * 4 + 30, panel_h), (250, 250, 250))
    for i, im in enumerate([src_small,
                            base.resize((panel_w, panel_h), Image.NEAREST),
                            neutral.resize((panel_w, panel_h), Image.NEAREST)]):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB"), (i * (panel_w + 10), 0))
    darr = np.ones((CH, CW, 4), np.uint8) * 255
    darr[diff] = [255, 0, 0, 255]
    sheet.paste(Image.fromarray(darr).resize((panel_w, panel_h), Image.NEAREST).convert("RGB"),
                (3 * (panel_w + 10), 0))
    sheet.save(os.path.join(DIAG, "neutral_check.png"))
    print("wrote layers/*.png, _diag/roles.png, _diag/neutral_check.png")

if __name__ == "__main__":
    main()
