"""Render the Pip animation pack: PNG frames, transparent GIFs, manifest, preview.

Run:
  python build.py                     render all 32 animations
  python build.py idle-blink          render one (or a list)

Outputs (into pip-animations/):
  frames/<name>/NN.png   transparent working-resolution frames (128x192)
  gifs/<name>.gif        transparent animated GIF (loops loop forever,
                         one-shots play once)
  poses/<id>.png         still strip of the reusable head poses
  poses/head-diagnostic.gif (+ frames)  pupil-pinned acceptance diagnostic
  manifest.json          per-animation frame sequence, per-frame durations,
                         totals, behaviour, start/end pose
  preview.html           offline gallery (data embedded, works from file://)
  source/_diag/strip_<name>_48.png / _96.png   motion check at display sizes
"""
import os, sys, json
import numpy as np
from PIL import Image

import riglib
from riglib import RIG, CW, CH
import motions

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, ".."))
GIF_DIR = os.path.join(OUT, "gifs")
FR_DIR = os.path.join(OUT, "frames")
POSE_DIR = os.path.join(OUT, "poses")
BASE_DIR = os.path.join(OUT, "baseline")
DIAG = os.path.join(HERE, "_diag")
os.makedirs(GIF_DIR, exist_ok=True)
os.makedirs(FR_DIR, exist_ok=True)
os.makedirs(POSE_DIR, exist_ok=True)
os.makedirs(DIAG, exist_ok=True)

KEY_INDEX = 12
KEY_COLOR = (255, 0, 255)
BASELINE_NAMES = ["look-left", "look-right", "look-up", "look-down",
                  "acknowledge", "listening", "curious", "confused", "success"]

def gif_palette():
    flat = []
    for c in riglib.CLASSES:
        flat.extend(riglib.PAL[c])
    flat.extend(KEY_COLOR)
    flat.extend([0] * (256 - len(riglib.CLASSES) - 1) * 3)
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal

PAL_IMG = gif_palette()

def to_p(img):
    arr = np.array(img)
    rgb = arr[..., :3].copy()
    rgb[arr[..., 3] == 0] = KEY_COLOR
    return Image.fromarray(rgb, "RGB").quantize(palette=PAL_IMG, dither=Image.Dither.NONE)

def compose_steps(steps):
    """Compose timeline steps, snap durations to 10 ms, merge identical frames."""
    frames, durs = [], []
    for p, ms in steps:
        frames.append(riglib.compose(p))
        durs.append(max(20, int(round(ms / 10.0)) * 10))
    merged, mdurs = [], []
    for img, ms in zip(frames, durs):
        if merged and np.array_equal(np.asarray(merged[-1]), np.asarray(img)):
            mdurs[-1] += ms
        else:
            merged.append(img)
            mdurs.append(ms)
    return merged, mdurs

def save_gif(path, frames, durs, behavior):
    pframes = [to_p(f) for f in frames]
    save_kw = dict(save_all=True, append_images=pframes[1:], duration=durs,
                   transparency=KEY_INDEX, disposal=2, optimize=False)
    if behavior == "loop":
        save_kw["loop"] = 0                       # repeat indefinitely
    pframes[0].save(path, **save_kw)

def write_frames(fdir, frames):
    if os.path.isdir(fdir):
        for old in os.listdir(fdir):              # clear stale frames from earlier runs
            if old.endswith(".png"):
                os.remove(os.path.join(fdir, old))
    os.makedirs(fdir, exist_ok=True)
    paths = []
    width = 2 if len(frames) < 100 else 3
    for i, img in enumerate(frames):
        img.save(os.path.join(fdir, "%0*d.png" % (width, i + 1)))
        paths.append("%0*d.png" % (width, i + 1))
    return paths

def render_one(entry):
    name, category, behavior, steps, start_pose, end_pose = entry
    frames, durs = compose_steps(steps)
    rels = [f"frames/{name}/{p}" for p in write_frames(os.path.join(FR_DIR, name), frames)]
    save_gif(os.path.join(GIF_DIR, name + ".gif"), frames, durs, behavior)
    strip(name, frames)
    return {
        "name": name,
        "file": f"gifs/{name}.gif",
        "category": category,
        "frames": rels,
        "durations_ms": durs,
        "total_ms": int(sum(durs)),
        "behavior": "loop" if behavior == "loop" else "one-shot",
        "start_pose": start_pose,
        "end_pose": end_pose,
    }

def render_pose_assets():
    """Still strip of the reusable head poses + the pupil-pinned head diagnostic."""
    stills = []
    for pid in motions.POSE_STILLS:
        img = riglib.compose(riglib.pose(head_pose=pid))
        img.save(os.path.join(POSE_DIR, pid + ".png"))
        stills.append({"id": pid,
                       "label": RIG["head_poses"][pid].get("label", pid),
                       "file": f"poses/{pid}.png"})
    frames, durs = compose_steps(motions.HEAD_DIAGNOSTIC)
    names = write_frames(os.path.join(POSE_DIR, "head-diagnostic"), frames)
    save_gif(os.path.join(POSE_DIR, "head-diagnostic.gif"), frames, durs, "loop")
    diag = {
        "file": "poses/head-diagnostic.gif",
        "frames": [f"poses/head-diagnostic/{n}" for n in names],
        "durations_ms": durs,
        "note": "pupils pinned at neutral - only the head silhouette carries meaning",
    }
    return stills, diag

def strip(name, frames):
    """Motion check sheets at 48 px and 96 px on light and dark backgrounds."""
    for h in (48, 96):
        w = int(round(CW * h / CH))
        tiles = []
        for f in frames:
            small = f.resize((w, h), Image.NEAREST)
            tiles.append(small)
        gap = 2
        sheet = Image.new("RGB", (len(tiles) * (w + gap) + gap, 2 * (h + gap) + gap), (255, 255, 255))
        dark = Image.new("RGB", (len(tiles) * (w + gap) + gap, h + gap), (18, 20, 28))
        sheet.paste(dark, (0, h + 2 * gap))
        for i, t in enumerate(tiles):
            x = gap + i * (w + gap)
            for row, y in ((0, gap), (1, h + 2 * gap)):
                bg = Image.new("RGBA", (w, h), (255, 255, 255, 255) if row == 0 else (18, 20, 28, 255))
                bg.alpha_composite(t)
                sheet.paste(bg.convert("RGB"), (x, y))
        sheet.save(os.path.join(DIAG, f"strip_{name}_{h}.png"))

def baseline_entry(name, after):
    """Before/after frame sequences for the preview's Head motion comparison."""
    bdir = os.path.join(BASE_DIR, "frames", name)
    frames = []
    if os.path.isdir(bdir):
        frames = [f"baseline/frames/{name}/{f}" for f in sorted(f for f in os.listdir(bdir) if f.endswith(".png"))]
    durs = []
    gpath = os.path.join(BASE_DIR, "gifs", name + ".gif")
    if os.path.exists(gpath):
        im = Image.open(gpath)
        for i in range(getattr(im, "n_frames", 1)):
            im.seek(i)
            durs.append(im.info.get("duration", 0))
    return {"name": name,
            "before": {"frames": frames, "durations_ms": durs},
            "after": {"frames": after["frames"], "durations_ms": after["durations_ms"]}}

def write_manifest(entries):
    manifest = {
        "character": "Pip (Azthreus robotic baby T. rex)",
        "canvas": [CW, CH],
        "working_scale": {
            "cell_px": RIG["grid"]["cell_px"],
            "note": "1 working pixel = 6 native pip.png pixels; motion happens in "
                    "whole working pixels, scaling is nearest-neighbour",
        },
        "ground": RIG["grid"]["ground"],
        "head_poses": {k: v.get("label", k) for k, v in RIG["head_poses"].items()},
        "animations": entries,
    }
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    return manifest

def write_preview(manifest, stills, diag, comparisons):
    tpl = open(os.path.join(HERE, "preview_template.html")).read()
    pack = {"manifest": manifest, "poses": stills, "diagnostic": diag,
            "head_motion": comparisons}
    html = tpl.replace("/*__PACK__*/", json.dumps(pack, indent=1))
    open(os.path.join(OUT, "preview.html"), "w").write(html)

def main():
    want = sys.argv[1:]
    entries = []
    for entry in motions.ANIMS:
        name = entry[0]
        if want and name not in want:
            continue
        rec = render_one(entry)
        entries.append(rec)
        print(f"rendered {name}: {len(rec['frames'])} frames, {rec['total_ms']} ms, {rec['behavior']}")
    stills, diag = render_pose_assets()
    print(f"pose stills: {len(stills)}  diagnostic: {len(diag['frames'])} frames")

    # manifest always describes the full set so preview/verify stay in sync
    full = []
    by_name = {e["name"]: e for e in entries}
    for entry in motions.ANIMS:
        if entry[0] in by_name:
            full.append(by_name[entry[0]])
            continue
        # not re-rendered in this run: describe the assets already on disk
        name, category, behavior, steps, sp, ep = entry
        gpath = os.path.join(GIF_DIR, name + ".gif")
        fdir = os.path.join(FR_DIR, name)
        durs, frame_paths = [], []
        if os.path.exists(gpath):
            im = Image.open(gpath)
            for i in range(getattr(im, "n_frames", 1)):
                im.seek(i)
                durs.append(im.info.get("duration", 0))
        if os.path.isdir(fdir):
            frame_paths = [f"frames/{name}/{f}" for f in sorted(f for f in os.listdir(fdir) if f.endswith(".png"))]
        if not durs:   # nothing rendered yet: merge adjacent identical pose steps
            merged = []
            for p, ms in steps:
                ms = max(20, int(round(ms / 10.0)) * 10)
                if merged and merged[-1][0] == riglib.snap(p):
                    merged[-1][1] += ms
                else:
                    merged.append([riglib.snap(p), ms])
            durs = [m[1] for m in merged]
        full.append({
            "name": name, "file": f"gifs/{name}.gif", "category": category,
            "frames": frame_paths, "durations_ms": durs, "total_ms": int(sum(durs)),
            "behavior": "loop" if behavior == "loop" else "one-shot",
            "start_pose": sp, "end_pose": ep,
        })
    manifest = write_manifest(full)
    by = {a["name"]: a for a in full}
    comparisons = [baseline_entry(n, by[n]) for n in BASELINE_NAMES]
    write_preview(manifest, stills, diag, comparisons)
    print(f"manifest.json + preview.html written ({len(full)} animations)")

if __name__ == "__main__":
    main()
