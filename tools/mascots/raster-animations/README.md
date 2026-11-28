# Raster — animation pack (`raster-animations/`)

## 1. What this is

A pack of **32 transparent animated GIFs** (96x96 px, pixel art) of **Raster**, the desktop AI
assistant robot (Azthreus Systems), plus a matching transparent RGBA **PNG frame sequence** per
animation. Everything is generated from editable parts by `source\render.py` — nothing here is
hand-keyed video. Open `raster-animations\preview.html` in a browser (works offline, double-click)
for a playable gallery, scrubbers, a light/dark stage, and the reference comparison.

- **12 loops:** `idle-blink`, `idle-look-around`, `idle-antenna-settle`, `listening`, `sleepy`,
  `thinking`, `searching`, `reading`, `typing`, `speaking`, `processing`, `waiting`
- **20 one-shots:** `idle-double-blink`, `notice`, `curious`, `idea`, `success`, `celebrate`,
  `acknowledge`, `unsure`, `confused`, `warning`, `error`, `encourage`, `look-left`, `look-right`,
  `look-up`, `look-down`, `hello`, `goodbye`, `wake-up`, `power-down`

## 2. Working resolution: 96x96 (72x72 was tested first and rejected)

Per the brief a **72x72** grid was tried first; `source\grid_test.py` reproduces that test and
prints the measurements:

- At **72 px** the dark wrist band rasterized to **~1 px** and the gripper jaw notch gap to
  **~2 px shallow** — the band visually disappeared and the notch nearly closed.
- At **96 px** the wrist band is **2-3 px** and the notch **3 px wide/deep** — both features
  survive the downscale.

**Chosen grid: 96x96 canvas, character 90 px tall, ground row y=91.**

Reproduce (from the repository root):

```powershell
python raster-animations\source\grid_test.py
```

It writes `source\_grid_test_72*.png` and `source\_grid_test_96*.png` (`*_annot.png` with
measurements, `*_arm10x.png` 10x arm zooms) for side-by-side inspection.

## 3. Regenerate ONE animation (example: `hello`)

```powershell
python raster-animations\source\render.py hello
```

## 4. Regenerate EVERYTHING (parts -> poses -> all clips)

```powershell
python raster-animations\source\make_parts.py
python raster-animations\source\make_poses.py
python raster-animations\source\render.py
```

## 5. Run the verification suite

```powershell
python raster-animations\source\verify.py
```

## 6. Regenerate the hello comparison image

```powershell
python raster-animations\source\compare_reference.py
```

Renders `source\_hello_compare.png` = sample robot vs Raster hello at equal height, aligned at the
waving shoulder. The reference GIF it compares against lives at
`references\mascots\wave\mascot-wave.gif` (path relative to `preview.html`:
`../references/mascots/wave/mascot-wave.gif`).

## 7. How to edit

- **Wrist / gripper shape:** edit the arm pose silhouettes
  `source\pose_art\<L|R>_r0..r7.png`, or add pixel fixes in `source\poses_corrections.json`
  (create the file if missing) without touching code:

  ```json
  {"edits": [{"pose": "R_r5", "set": [[x, y, "#hex"]], "clear": [[x, y]]}]}
  ```

- **Wave holds / timing:** edit the millisecond values in `source\timelines.py` — each clip is a
  list of `(state, duration_ms)` entries, e.g. `hello` holds `r7`/`r5` wave poses at 110 ms each.
- **Rebuild just that clip** (updates `frames\`, `gifs\` and `manifest.json`):

  ```powershell
  python raster-animations\source\render.py <name>
  ```

## 8. File map

```
raster-animations\
  gifs\                 32 transparent animated GIFs (the deliverable)
  frames\<name>\NNN.png transparent RGBA frames at 96x96 (drive preview.html's players)
  manifest.json         per animation: name, filename, mode ("loop"|"once"), frames,
                        frame_count, durations_ms, total_ms, start_pose, end_pose
  preview.html          offline gallery + scrubbers + reference comparison + power-down->wake-up
  README.md             this file
  source\
    parts\              editable character layers cut from raster.png
    pose_art\           16 editable arm poses (L_r0..r7, R_r0..r7)
    parts.json          part pivots / placement
    palette.json        fixed palette + signal cue ramps
    timelines.py        all 32 clip timelines (state, duration_ms)
    make_parts.py       cuts raster.png into parts
    make_poses.py       renders the arm pose silhouettes
    rasterize.py        palette rasterization helpers
    arm_model.py        arm chain + pose ladder + poses_corrections.json application
    render.py           renderer + GIF encoder (single source of truth for output)
    verify.py           verification suite
    compare_reference.py  renders _hello_compare.png
    contact_sheet.py    contact sheet generator
    grid_test.py        reproduces the 72 vs 96 grid decision
```

## 9. Arm naming and pose ladder

- `armL` = **viewer's left** = Raster's **anatomical right** (static in `hello`).
- `armR` = **viewer's right** = Raster's **anatomical left** — the `hello`/`goodbye` wave arm.
- Poses `r0..r7` = **0, 22, 45, 68, 90, 110, 121, 133 degrees** of swing out of vertical toward
  the arm's outward side. `r6` = "hand beside the lower edge of the CRT".

## 10. Palette

`source\palette.json` holds the fixed character palette plus the animated signal ramps, applied
through the eye / antenna / chest-lamp masks:

- **Normal signal ramp:** `#f2ff20 #ececa3 #b5e550 #abc32f #809c13 #607c3c #0eff00 #1fc600 #089000 #0a5d00 #063b00`
- **Warning / error ramp:** `#bbdb44 #f7e379 #f2a134 #e51f1f`
