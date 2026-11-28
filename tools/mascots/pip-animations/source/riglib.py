"""Shared Pip rig library: palette, layers, pose model, frame compositor.

Used by layers.py (builds the layer PNGs), build.py (renders the pack) and
verify.py (checks the exports). Motion parameters live in rig.json, the 32
timelines live in motions.py.
"""
import os, json
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
RIG = json.load(open(os.path.join(HERE, "rig.json")))
PAL = json.load(open(os.path.join(HERE, "palette.json")))

GRID = RIG["grid"]
CW, CH = GRID["canvas"]
CELL = GRID["cell_px"]
ORIGIN = tuple(GRID["origin"])
GROUND = GRID["ground"]

# stable class order (also the GIF palette order)
CLASSES = ["outline_dark", "plate_dark", "blue_mid", "blue_shade", "blue_deep",
           "blue_pale", "blue_light", "mint", "orange", "ivory", "white", "gray"]
RGBA = {k: tuple(PAL[k]) + (255,) for k in CLASSES}
DARK = RGBA["outline_dark"]        # faceplate / outline
FACE = RGBA["outline_dark"]

_cache = {}
def layer(name):
    if name not in _cache:
        _cache[name] = Image.open(os.path.join(HERE, "layers", name + ".png")).convert("RGBA")
    return _cache[name].copy()

# ------------------------------------------------------------------ pose
POSE0 = {
    "body_dy": 0,             # whole-body hop offset (cells, negative = up)
    "head_dx": 0, "head_dy": 0, "head_rot": 0.0,
    "head_pose": "neutral",   # neutral | turn_L | turn_R | chin_up | chin_up_soft | chin_down | tilt
    "tail_rot": 0.0,
    "arm_n": [0, 0, 0.0],     # near forearm dx, dy, rot(deg)
    "arm_f": [0, 0, 0.0],     # far forearm dx, dy, rot(deg)
    "gaze": [0, 0],           # pupil offset (cells) for both eyes
    "conv": 0,                # viewer convergence (cells)
    "lid": [0.0, 0.0],        # left/right eye lid fraction 0..1
    "mouth": "R",             # C closed / R resting / S slightly open
}

def pose(**kw):
    p = json.loads(json.dumps(POSE0))
    p.update(kw)
    return p

def lerp_pose(a, b, t):
    p = pose()
    for k in ("body_dy", "head_dx", "head_dy", "head_rot", "tail_rot", "conv"):
        p[k] = a[k] + (b[k] - a[k]) * t
    for k in ("arm_n", "arm_f", "gaze", "lid"):
        p[k] = [a[k][i] + (b[k][i] - a[k][i]) * t for i in range(len(a[k]))]
    p["mouth"] = b["mouth"] if t >= 1 else a["mouth"]
    p["head_pose"] = b["head_pose"] if t >= 1 else a["head_pose"]
    return p

def snap(p):
    """Whole working-grid pixels for translations; 0.5 deg steps for angles."""
    q = json.loads(json.dumps(p))
    for k in ("body_dy", "head_dx", "head_dy", "conv"):
        q[k] = int(round(q[k]))
    for k in ("head_rot", "tail_rot"):
        q[k] = round(q[k] * 2) / 2
    q["arm_n"] = [int(round(q["arm_n"][0])), int(round(q["arm_n"][1])), round(q["arm_n"][2] * 2) / 2]
    q["arm_f"] = [int(round(q["arm_f"][0])), int(round(q["arm_f"][1])), round(q["arm_f"][2] * 2) / 2]
    q["gaze"] = [int(round(v)) for v in q["gaze"]]
    return q

# ------------------------------------------------------------------ helpers
def squeeze_cols(img, x0, s):
    """Foreshorten (s<1) or stretch (s>1) every column right of x0 (yaw turn).
    Inverse-mapped so the result stays whole working-grid pixels."""
    if abs(s - 1.0) < 1e-6:
        return img
    arr = np.array(img)
    out = arr.copy()
    out[:, x0:] = 0
    for x in range(x0, img.width):
        si = min(int(round(x0 + (x - x0) / s)), img.width - 1)
        out[:, x] = arr[:, si]
    return Image.fromarray(out, "RGBA")

def shift_zones(img, zones, shifts):
    """Pitch shear: shift whole row zones and fill/overlap seams (never a tear)."""
    src = np.array(img)
    dst = np.zeros_like(src)
    prev_end = None
    for (y0, y1), s in zip(zones, shifts):
        block = src[y0:y1 + 1]
        ty0 = y0 + s
        if prev_end is not None and ty0 > prev_end + 1:
            for y in range(prev_end + 1, ty0):
                if 0 <= y < CH:
                    dst[y] = dst[prev_end]
        for i in range(block.shape[0]):
            y = ty0 + i
            if 0 <= y < CH:
                row = block[i]
                keep = (dst[y, :, 3] == 0) | (row[:, 3] > 0)
                dst[y][keep] = row[keep]
        prev_end = ty0 + block.shape[0] - 1
    return Image.fromarray(dst, "RGBA")

def head_pose_geom(head_pose):
    """Per-pose head geometry: which head layer, eye/mouth offsets, far-eye width,
    snout squeeze and any extra roll. Everything derives from rig.json."""
    hp = RIG["head_poses"].get(head_pose) or {}
    zs = hp.get("zone_shift", [0, 0, 0, 0])
    name = "head" if not (hp.get("snout_squeeze") or hp.get("zone_shift")) else "head_%s" % head_pose
    return {
        "layer": name,
        "eye_dy": zs[1],
        "far_eye_dw": hp.get("far_eye_dw", 0),
        "mouth_dy": zs[2],
        "squeeze": (hp.get("snout_x0", 82), hp.get("snout_squeeze", 1.0)),
        "extra_rot": hp.get("head_rot", 0.0),
    }

def _rot(img, deg, pivot):
    """Rotate around pivot (cell coords), counter-clockwise positive (PIL)."""
    if abs(deg) < 1e-6:
        return img
    return img.rotate(-deg, resample=Image.NEAREST,
                      center=(pivot[0] + 0.5, pivot[1] + 0.5),
                      fillcolor=(0, 0, 0, 0))

def _shift(img, dx, dy):
    if dx == 0 and dy == 0:
        return img
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (int(dx), int(dy)))
    return out

def _draw_eye(asm, side, p, geom):
    """Draw one eye: mint shape, pupil+catchlight unit, lid cover + mint lid mark.

    Closing replaces the mint shape with a short mint lid mark on the preserved
    dark faceplate; the catchlight never separates from its pupil. Head poses may
    shift the eye and change how much of the far eye shows (far_eye_dw)."""
    e = RIG["eyes"][side]
    x0, y0, x1, y1 = e["bbox"]
    px0, py0, px1, py1 = e["pupil"]
    dy = geom["eye_dy"]
    dw = geom["far_eye_dw"] if side == RIG["far_eye"] else 0
    x0, y0, x1, y1 = x0, y0 + dy, x1 + (dw if dw > 0 else 0), y1 + dy
    gx, gy = p["gaze"]
    conv = p["conv"] * (1 if side == "L" else -1)
    cx = RIG["eyes"]["gaze_clamp_x"]
    cy = RIG["eyes"]["gaze_clamp_y"]
    b = e["bbox"]
    dx = max(-cx, min(cx, gx + conv))
    dyy = max(-cy, min(cy, gy))
    # keep the pupil inside the mint shape (unshifted geometry, then the pose shifts)
    dx = max(b[0] - px0, min(b[2] - px1, dx))
    dyy = max(b[1] - py0, min(b[3] - py1, dyy))

    asm.alpha_composite(_shift(layer("eye%s_mint" % side), 0, dy))
    if dw > 0:                       # more of the far eye visible: widen the middle row
        mr = e["mint_rects"][1]
        ImageDraw.Draw(asm).rectangle([mr[2] + 1, mr[1] + dy, mr[2] + dw, mr[3] + dy],
                                      fill=RGBA["mint"])
    asm.alpha_composite(_shift(layer("eye%s_pupil" % side), dx, dyy + dy))
    if dw < 0:                       # less far eye visible: faceplate covers its outer edge
        b = e["bbox"]
        ImageDraw.Draw(asm).rectangle([b[2] + dw + 1, b[1] + dy, b[2], b[3] + dy], fill=FACE)

    lid = p["lid"][0 if side == "L" else 1]
    if lid <= 0:
        return
    ly0 = e["lid_row"][0] + dy                   # rest position of the lid mark
    if lid >= 1:
        dash_y, cover_bottom = ly0, y1 + 1       # fully closed: mark at eye centre
    else:
        dash_y = y0 + 2 + int(round((ly0 - y0 - 2) * lid))
        cover_bottom = dash_y + 2                # mark rides the lid edge
    d = ImageDraw.Draw(asm)
    d.rectangle([e["bbox"][0], y0, e["bbox"][2] + max(dw, 0), cover_bottom - 1], fill=FACE)
    lidimg = _shift(layer("lid%s" % side), 0, dash_y - e["lid_row"][0])
    if dw > 0:
        ex = e["lid_span"][1]
        ImageDraw.Draw(lidimg).rectangle([ex + 1, e["lid_row"][0], ex + dw, e["lid_row"][1]],
                                         fill=RGBA["mint"])
    elif dw < 0:
        ex = e["lid_span"][1]
        ImageDraw.Draw(lidimg).rectangle([ex + dw + 1, e["lid_row"][0] - 4, ex, e["lid_row"][1] + 4],
                                         fill=(0, 0, 0, 0))
    asm.alpha_composite(lidimg)

def compose(p):
    """Composite one frame (RGBA, whole working-grid pixels)."""
    p = snap(p)
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    by = p["body_dy"]
    piv = {k: tuple(v) for k, v in RIG["pivots"].items()}
    geom = head_pose_geom(p["head_pose"])

    # tail sits behind the body: its root hides under the shared hip silhouette
    tail = _rot(layer("tail"), p["tail_rot"], piv["tail"])
    canvas.alpha_composite(_shift(tail, 0, by))

    canvas.alpha_composite(_shift(layer("body"), 0, by))

    for key, img_name, piv_name in (("arm_f", "arm_far", "arm_far"), ("arm_n", "arm_near", "arm_near")):
        dx, dy, deg = p[key]
        arm = _rot(layer(img_name), deg, piv[piv_name])
        canvas.alpha_composite(_shift(arm, dx, by + dy))

    head = layer(geom["layer"])
    mouth = squeeze_cols(layer("mouth_%s" % p["mouth"]), *geom["squeeze"])
    head.alpha_composite(_shift(mouth, 0, geom["mouth_dy"]))
    _draw_eye(head, "L", p, geom)
    _draw_eye(head, "R", p, geom)
    head = _rot(head, p["head_rot"] + geom["extra_rot"], piv["neck"])
    canvas.alpha_composite(_shift(head, p["head_dx"], by + p["head_dy"]))
    return canvas
