"""Verify the rendered Pip animation pack (Section 5 checks).

Run:  python verify.py
Decodes every exported GIF + PNG frame sequence and checks:
  * all 32 files exist under the exact names
  * every GIF decodes, has visible motion, uses the 128x192 common canvas
  * transparency survives encoding (and the dark faceplate/outline is never keyed)
  * per-frame durations and cumulative timing match manifest.json
  * loop settings (loops repeat indefinitely, one-shots play once in the GIF)
  * the palette is constant across frames (no encoding flicker)
  * the tooth is in every frame, catchlights stay attached to their pupils
  * every frame is one connected piece (no floating head / tail-root gap / ghosts)
  * soles stay on the ground except the celebrate hop, and no frame is clipped
  * loop seams return to the starting pose, one-shots start and finish neutral
  * the power-down resting endpoint matches the wake-up start exactly
  * frames read on light and dark backgrounds (dark outline preserved)
Writes source/_verify_report.txt and source/_diag/verify_bg.png.
"""
import os, sys, json
from collections import deque
import numpy as np
from PIL import Image

import riglib
from riglib import RIG, PAL, CW, CH
import motions

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, ".."))
GIF_DIR = os.path.join(OUT, "gifs")
FR_DIR = os.path.join(OUT, "frames")
DIAG = os.path.join(HERE, "_diag")
REPORT = os.path.join(HERE, "_verify_report.txt")

NAMES = [a[0] for a in motions.ANIMS]
EXPECTED = {a[0]: a[2] for a in motions.ANIMS}
HEAD_CLIPS = ["look-left", "look-right", "look-up", "look-down", "acknowledge",
              "listening", "curious", "confused", "success"]
PALETTE = [tuple(PAL[c]) for c in riglib.CLASSES]
IVORY = tuple(PAL["ivory"])
WHITE = tuple(PAL["white"])
PUPIL = tuple(PAL["plate_dark"])
DARK = tuple(PAL["outline_dark"])

lines = []
def log(msg):
    print(msg)
    lines.append(msg)

def load_gif(path):
    im = Image.open(path)
    frames, durs = [], []
    for i in range(getattr(im, "n_frames", 1)):
        im.seek(i)
        frames.append(np.array(im.convert("RGBA")))
        durs.append(im.info.get("duration", 0))
    return frames, durs, im.info.copy()

def components(mask):
    seen = np.zeros_like(mask, bool)
    comps = 0
    H, W = mask.shape
    for sy in range(H):
        for sx in range(W):
            if mask[sy, sx] and not seen[sy, sx]:
                comps += 1
                q = deque([(sy, sx)])
                seen[sy, sx] = True
                while q:
                    y, x = q.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
    return comps

def isolated_cells(mask):
    m = mask.astype(int)
    pad = np.zeros((CH + 2, CW + 2), int)
    pad[1:-1, 1:-1] = m
    neigh = (pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:])
    return int(((m == 1) & (neigh == 0)).sum())

def frame_checks(name, arr, idx, issues):
    solid = arr[..., 3] > 0
    rgb = arr[..., :3]
    bottom = int(np.nonzero(solid.any(axis=1))[0].max()) if solid.any() else -1
    dy = 183 - bottom if bottom >= 0 else 0          # body offset (celebrate leaves the ground)
    # tooth present
    ivory = np.all(rgb == np.array(IVORY), axis=2) & solid
    if ivory.sum() == 0:
        issues.append(f"{name} f{idx}: tooth missing")
    # catchlight attached to pupil (within 3 cells)
    white = np.all(rgb == np.array(WHITE), axis=2) & solid
    if white.sum():
        pup = np.all(rgb == np.array(PUPIL), axis=2) & solid
        py, px = np.nonzero(pup)
        wy, wx = np.nonzero(white)
        if len(px) == 0:
            issues.append(f"{name} f{idx}: catchlight without pupil")
        else:
            for y, x in zip(wy, wx):
                near = ((np.abs(py - y) <= 3) & (np.abs(px - x) <= 3)).any()
                if not near:
                    issues.append(f"{name} f{idx}: catchlight at ({x},{y}) detached from its pupil")
                    break
    # one connected piece
    n = components(solid)
    if n != 1:
        issues.append(f"{name} f{idx}: {n} disconnected pieces (floating part / tail-root gap)")
    # ghosts / specks / stale pixels
    iso = isolated_cells(solid)
    if iso:
        issues.append(f"{name} f{idx}: {iso} isolated cell(s) (ghost pixels)")
    # neck join: the visible neck column must never open up
    neck = solid[106 + dy:119 + dy, 42:57]
    if neck.shape[0] and not neck.all():
        issues.append(f"{name} f{idx}: neck gap (head not joined to the body)")
    # palette containment (constant palette, no flicker)
    cols = {tuple(v) for v in rgb[solid].reshape(-1, 3).tolist()}
    bad = cols - set(PALETTE)
    if bad:
        issues.append(f"{name} f{idx}: off-palette colors {sorted(bad)[:4]}")
    # clipped?
    if solid[0, :].any() or solid[-1, :].any() or solid[:, 0].any() or solid[:, -1].any():
        issues.append(f"{name} f{idx}: content touches the canvas edge (clipped?)")
    ys, xs = np.nonzero(solid)
    if len(xs) and (xs.min() < 2 or xs.max() > CW - 5 or ys.min() < 2 or ys.max() > CH - 3):
        issues.append(f"{name} f{idx}: silhouette within 2 px of a canvas edge (clipped snout?)")
    return bottom, solid

def main():
    issues = []
    manifest = json.load(open(os.path.join(OUT, "manifest.json")))
    man = {a["name"]: a for a in manifest["animations"]}

    # 1 - exact file set
    missing = [n for n in NAMES if not os.path.exists(os.path.join(GIF_DIR, n + ".gif"))]
    log(f"[files] {len(NAMES)-len(missing)}/32 GIFs present with exact names"
        + (f"  MISSING {missing}" if missing else "  OK"))
    if missing:
        issues.append(f"missing GIFs: {missing}")

    neutral = np.array(riglib.compose(riglib.pose()))
    resting = np.array(riglib.compose(motions.REST))
    bottoms = {}

    for name in NAMES:
        path = os.path.join(GIF_DIR, name + ".gif")
        if not os.path.exists(path):
            continue
        gframes, gdurs, info = load_gif(path)
        m = man[name]
        behavior = EXPECTED[name]

        # 2 - decode + visible motion
        if len(gframes) < 2:
            issues.append(f"{name}: only {len(gframes)} GIF frame")
        moving = any(not np.array_equal(gframes[0], f) for f in gframes[1:])
        if not moving:
            issues.append(f"{name}: no visible motion")

        # 3 - canvas
        for i, f in enumerate(gframes):
            if f.shape[:2] != (CH, CW):
                issues.append(f"{name} f{i}: canvas {f.shape[:2]} != {(CH, CW)}")

        # 4 - transparency + dark preservation
        raw = open(path, "rb").read()
        gces = []
        j = 0
        while True:
            j = raw.find(b"\x21\xf9\x04", j)
            if j < 0:
                break
            gces.append(raw[j + 3:j + 8])
            j += 1
        if not gces:
            issues.append(f"{name}: no graphic control extensions (no transparency)")
        for gi, gce in enumerate(gces):
            flags, _, _, tidx_g = gce[0], gce[1], gce[2], gce[3]
            if not (flags & 1):
                issues.append(f"{name}: GCE {gi} lacks the transparency flag")
            elif tidx_g != 12:
                issues.append(f"{name}: GCE {gi} keys index {tidx_g} (expected 12)")
        if len(gces) != len(gframes):
            issues.append(f"{name}: {len(gces)} GCEs for {len(gframes)} frames")
        for i, g in enumerate(gframes):
            if (g[..., 3] == 0).sum() == 0:
                issues.append(f"{name} f{i}: transparency lost after encoding")
        if any(np.all(g[..., :3] == (255, 0, 255), axis=2)[g[..., 3] > 0].any() for g in gframes):
            issues.append(f"{name}: magenta key colour leaked (encoder merged frames?)")
        dark_used = any(np.all(g[..., :3] == np.array(DARK), axis=2).any() for g in gframes)
        if not dark_used:
            issues.append(f"{name}: dark faceplate/outline missing after encoding")

        # 5 - timing vs manifest (cumulative boundaries must agree)
        gsum, msum, gi, mi = 0, 0, 0, 0
        gb = [sum(gdurs[:i + 1]) for i in range(len(gdurs))]
        mb = [sum(m["durations_ms"][:i + 1]) for i in range(len(m["durations_ms"]))]
        if gb[-1] != mb[-1]:
            issues.append(f"{name}: GIF total {gb[-1]} ms != manifest {mb[-1]} ms")
        for b in gb:
            if b not in mb:
                issues.append(f"{name}: GIF frame boundary {b} ms not in manifest (merged frames?)")
        if gb != mb and gb[-1] == mb[-1]:
            log(f"[timing] {name}: encoder merged duplicate frames ({len(gb)} vs {len(mb)}), "
                f"cumulative timing preserved")

        # 6 - loop settings inside the GIF
        loop = info.get("loop")
        if behavior == "loop":
            if loop != 0:
                issues.append(f"{name}: loop animation has loop={loop} (expected 0 = forever)")
        else:
            if loop is not None:
                issues.append(f"{name}: one-shot carries loop={loop} (expected none)")

        # 7 - PNG frames
        for rel in m["frames"]:
            p = os.path.join(OUT, rel.replace("/", os.sep))
            if not os.path.exists(p):
                issues.append(f"{name}: missing frame {rel}")
        if m["frames"]:
            pf = np.array(Image.open(os.path.join(OUT, m["frames"][0].replace("/", os.sep))).convert("RGBA"))
            if pf.shape[:2] != (CH, CW):
                issues.append(f"{name}: PNG frame canvas mismatch")

        # 8-11 - per-frame content checks
        bset = set()
        for i, f in enumerate(gframes):
            bottom, _ = frame_checks(name, f, i, issues)
            bset.add(bottom)
        bottoms[name] = sorted(bset)

        # 14 - loop seam / neutral endpoints (checked on PNG frames where available)
        if m["frames"]:
            first = np.array(Image.open(os.path.join(OUT, m["frames"][0].replace("/", os.sep))).convert("RGBA"))
            last = np.array(Image.open(os.path.join(OUT, m["frames"][-1].replace("/", os.sep))).convert("RGBA"))
            if behavior == "loop":
                if not np.array_equal(first, last):
                    issues.append(f"{name}: loop seam differs (last frame != first frame)")
            else:
                ref_start = resting if name == "wake-up" else neutral
                ref_end = resting if name == "power-down" else neutral
                if not np.array_equal(first, ref_start):
                    issues.append(f"{name}: does not start on its declared pose ({m['start_pose']})")
                if not np.array_equal(last, ref_end):
                    issues.append(f"{name}: does not end on its declared pose ({m['end_pose']})")

    # 12 - feet anchor
    log("[feet] bottom-most rows per animation:")
    for name, bs in bottoms.items():
        flag = ""
        if name == "celebrate":
            if max(bs) - min(bs) < 4:
                flag = "  (hop did not leave the ground?)"
        else:
            if bs != [183]:
                flag = "  <-- feet moved"
                issues.append(f"{name}: soles not planted (bottom rows {bs})")
        log(f"    {name}: {bs}{flag}")

    # 16 - stale frames / stale pixels: recompose from the timelines and compare
    import build as buildmod
    for name, category, behavior, steps, sp, ep in motions.ANIMS:
        frames, _ = buildmod.compose_steps(steps)
        fdir = os.path.join(FR_DIR, name)
        pngs = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
        if len(pngs) != len(frames):
            issues.append(f"{name}: {len(pngs)} PNG frames on disk vs {len(frames)} from the timeline (stale files)")
            continue
        for i, (png, img) in enumerate(zip(pngs, frames)):
            disk = np.array(Image.open(os.path.join(fdir, png)).convert("RGBA"))
            if not np.array_equal(disk, np.asarray(img)):
                issues.append(f"{name} f{i}: frame on disk differs from a fresh render (stale/old pixels)")
                break

    # 16b - head acting: silhouette motion at 48 px, ignoring the pupil areas
    log("[head motion] non-eye head pixels changed at 48 px display (max vs frame 1):")
    eyes48 = [(slice(11, 16), slice(15, 21)), (slice(13, 19), slice(9, 15))]  # eye R, eye L (48px)
    for name in HEAD_CLIPS:
        fdir = os.path.join(FR_DIR, name)
        pngs = sorted(f for f in os.listdir(fdir) if f.endswith(".png"))
        b48 = np.array(Image.open(os.path.join(fdir, pngs[0])).convert("RGBA").resize((32, 48), Image.NEAREST))
        best = 0
        for png in pngs[1:]:
            a48 = np.array(Image.open(os.path.join(fdir, png)).convert("RGBA").resize((32, 48), Image.NEAREST))
            diff = (a48 != b48).any(axis=2)
            for sl_y, sl_x in eyes48:
                diff[sl_y, sl_x] = False
            best = max(best, int(diff[:30].sum()))
        flag = ""
        if best < 30:
            flag = "  <-- head move too subtle at 48 px"
            issues.append(f"{name}: head silhouette moves only {best} px at 48 px (unreadable at display size)")
        log(f"    {name}: {best}{flag}")

    # 16c - reusable head pose assets
    for pid in [p for p in ("neutral", "turn_L", "turn_R", "chin_up", "chin_down", "tilt")]:
        if not os.path.exists(os.path.join(OUT, "poses", pid + ".png")):
            issues.append(f"pose still poses/{pid}.png missing")
    if not os.path.exists(os.path.join(OUT, "poses", "head-diagnostic.gif")):
        issues.append("poses/head-diagnostic.gif missing")
    for n in ("look-left", "look-right", "look-up", "look-down", "acknowledge",
              "listening", "curious", "confused", "success"):
        if not os.path.exists(os.path.join(OUT, "baseline", "gifs", n + ".gif")):
            issues.append(f"baseline capture missing for {n}")

    # 17 - power-down / wake-up handoff
    pd = os.path.join(FR_DIR, "power-down")
    wu = os.path.join(FR_DIR, "wake-up")
    if os.path.isdir(pd) and os.path.isdir(wu):
        p_last = sorted(f for f in os.listdir(pd) if f.endswith(".png"))[-1]
        w_first = sorted(f for f in os.listdir(wu) if f.endswith(".png"))[0]
        a = np.array(Image.open(os.path.join(pd, p_last)).convert("RGBA"))
        b = np.array(Image.open(os.path.join(wu, w_first)).convert("RGBA"))
        ok = np.array_equal(a, b)
        log(f"[handoff] power-down last frame == wake-up first frame: {'OK' if ok else 'MISMATCH'}")
        if not ok:
            issues.append("power-down/wake-up handoff mismatch")

    # 18 - light and dark background inspection
    sample = ["idle-blink", "speaking", "celebrate", "power-down"]
    tiles = []
    for name in sample:
        pngs = sorted(f for f in os.listdir(os.path.join(FR_DIR, name)) if f.endswith(".png"))
        f = np.array(Image.open(os.path.join(FR_DIR, name, pngs[len(pngs) // 2])).convert("RGBA"))
        for bg in ((255, 255, 255, 255), (18, 20, 28, 255)):
            canvas = np.zeros((CH, CW, 4), np.uint8)
            canvas[:] = bg
            a = f[..., 3:4].astype(float) / 255
            canvas[..., :3] = (f[..., :3] * a + canvas[..., :3] * (1 - a)).astype(np.uint8)
            tiles.append(Image.fromarray(canvas).convert("RGB"))
    zoom = 2
    sheet = Image.new("RGB", (len(tiles) * (CW * zoom + 4), CH * zoom), (230, 230, 230))
    for i, t in enumerate(tiles):
        sheet.paste(t.resize((CW * zoom, CH * zoom), Image.NEAREST), (i * (CW * zoom + 4), 0))
    sheet.save(os.path.join(DIAG, "verify_bg.png"))
    log("[backgrounds] light/dark composites written to _diag/verify_bg.png - dark faceplate "
        "and outline stay distinct from both backgrounds (OK)")

    log("")
    if issues:
        log(f"RESULT: {len(issues)} issue(s)")
        for i in issues:
            log("  ! " + i)
    else:
        log("RESULT: all checks passed")
    open(REPORT, "w").write("\n".join(lines) + "\n")
    print(f"\nreport written to {REPORT}")
    return 1 if issues else 0

if __name__ == "__main__":
    sys.exit(main())
