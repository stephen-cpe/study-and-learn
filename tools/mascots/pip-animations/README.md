# Pip — animation pack

32 reusable transparent animations of **Pip**, the Azthreus robotic baby T. rex,
all rendered from the approved model `../pip.png` (which is left untouched).

```
pip-animations/
  gifs/                  32 transparent animated GIFs (exact filenames)
  frames/<name>/         numbered transparent PNG frames, 128x192 working canvas
  source/                editable layers/masks, shared motion definitions, scripts
  manifest.json          per-animation frames, per-frame durations, totals,
                         loop/one-shot behaviour, start and end pose
  preview.html           offline gallery (open directly from disk, no server)
  README.md              this file
```

## Head acting pass (yaw / pitch / roll poses)

The rig carries six reusable head poses (`source/rig.json` → `head_poses`,
baked as layers `source/layers/head_*.png`):

| Pose | What changes | Reused by |
|---|---|---|
| `neutral` | the approved model pose, preserved exactly | every entry/exit |
| `turn_L` | projected snout foreshortens (columns ≥ 82 squeezed to 0.75), far eye 3 cells wider | look-left, curious |
| `turn_R` | snout stretches to 1.20 (a little more profile), far eye 3 cells narrower | look-right |
| `chin_up` / `chin_down` | whole-row pitch shear at the gray neck (snout lifts/dips, neck exposure changes) | look-up, look-down, the nods |
| `chin_up_soft` | half-magnitude rebound | acknowledge, success |
| `tilt` | sideways roll −6° (the listening signature, never used as a turn) | listening |

Turns change the snout outline and the amount of far eye; chin poses pivot at the
gray neck and change the neck exposure; the tilt slants the eye line — the three
families stay distinct even with the pupils pinned (`poses/head-diagnostic.gif`).
Rows shift as whole rows with seam fill and the snout squeeze is inverse-mapped,
so no pose is a flat cutout; the cheek keeps its side, the tooth rides the mouth
patch and the catchlights ride their pupils.

`preview.html` has a **Head motion** section: baseline vs revised clips side by
side at 48 px and 96 px with synchronized replay (baselines captured in
`baseline/` before the exports were overwritten), the still pose strip
(`poses/neutral.png` … `poses/tilt.png`) and the pupil-pinned diagnostic player.

## Regenerate the pack

Everything runs with Python 3 + Pillow + numpy. Commands work from any
directory (paths resolve relative to the script).

```powershell
# full pipeline from pip.png
python pip-animations/source/layers.py        # pip.png -> editable layers + neutral check
python pip-animations/source/build.py         # render all 32: frames, GIFs, manifest, preview
python pip-animations/source/verify.py        # decode + verify the exported files

# a single animation (or a list) - rewrites that GIF + frames and refreshes manifest/preview
python pip-animations/source/build.py idle-blink
python pip-animations/source/build.py idle-blink listening speaking success celebrate
```

Diagnostic helpers in `source/`: `analyze.py` (lattice/palette study), `probe.py`
(feature measurement), `rle.py` / `gridmap.py` (working-grid dumps), `quantize.py`
(palette derivation + scale tests). Their output lands in `source/_diag/`.
`verify.py` writes `source/_verify_report.txt`.

## Working scale

* **1 working pixel = 6 native `pip.png` pixels.** Frames, layers and GIFs are
  authored on a **128 x 192** grid with the soles on ground row 184.
* `pip.png` has **no consistent underlying pixel grid**: its block motifs measure
  27–38 native px (catchlights 22 px, tooth 37 px, cheek 49x56 px, outline
  27–33 px). Downsampling was tested at 5, 6 and 8 native px per cell; the 6-px
  cell keeps every identity feature at 3–7 cells (eye highlights 4x4, tooth 6x6,
  cheek 10x8, nostrils 5x8, thick outline) and keeps the sprite above 100 cells
  tall, so the chosen resolution preserves the eye highlights, tooth, cheek mark
  and outline exactly as required.
* Motion happens in **whole working-grid pixels** (pupil offsets, head/arm/tail
  steps, hop height); angles are snapped to 0.5°. All scaling is nearest-neighbour
  (`image-rendering: pixelated` in the preview), and every frame is quantized to
  Pip's fixed 12-colour palette from `source/palette.json` — no per-frame
  re-quantization, so nothing flickers between frames.

## Where to edit

| What | File | Keys / area |
|---|---|---|
| Head poses (turn / chin / tilt) | `source/rig.json` | `head_poses`, `head_pose_zones`, `far_eye` |
| Blink timing | `source/rig.json` | `timing.blink_half_ms`, `blink_close_ms`, `blink_open_ms`, `blink_hold_ms` |
| Pupil offsets & gazes | `source/rig.json` | `eyes.gazes`, `eyes.gaze_clamp_*`, `eyes.viewer_converge` |
| Neck pivot (head rotation) | `source/rig.json` | `pivots.neck` (centre of the visible gray bolt) |
| Tail motion | `source/rig.json` | `motion.tail_sway_deg`, `tail_settle_deg`, `tail_wag_deg`, `pivots.tail` |
| Hop / nod / tilt amounts | `source/rig.json` | `motion.*` |
| Eye, lid and mouth shapes | `source/rig.json` | `eyes.L/R` (mint rects, pupil, catchlight, lid), `mouth.*` |
| Part cut lines (head/tail/arms) | `source/rig.json` | `cuts.*` |
| Palette | `source/palette.json` | 12 named colours used by every frame |
| The 32 timelines | `source/motions.py` | one entry per animation: pose steps + durations (ms) |
| Layer assembly / tooth table | `source/layers.py` | `TOOTH_ROWS`, `part_cells()` |
| Poses & compositing order | `source/riglib.py` | `POSE0`, `compose()` |
| GIF encoding (palette, loop, disposal) | `source/build.py` | `to_p()`, `render_one()` |
| Preview UI | `source/preview_template.html` | rebuilt into `preview.html` by `build.py` |

After edits run `layers.py` (if shapes/cuts changed), then `build.py`, then
`verify.py`. Pose fields (see `riglib.POSE0`): `body_dy`, `head_dx/dy/rot`,
`head_pose` (the reusable head poses above), `tail_rot`,
`arm_n`/`arm_f` (dx, dy, rot), `gaze`, `conv` (viewer convergence),
`lid` (per-eye 0..1), `mouth` (`C` closed / `R` resting / `S` slightly open).

## Rig anatomy (grounded in `pip.png`)

Head + snout, faceplate, mint eyes + square pupils + attached catchlights, mouth
seam + single ivory tooth, orange cheek, nostrils, gray neck bolt (head pivot),
torso + pale belly + broad feet (ground anchor), two tiny forearms, and the
upturned screen-right tail pivoting where it emerges from the torso. The tail
root and hip share one silhouette; only the small root patch is reconstructed so
the tail stays connected at every angle. Closing the eyes replaces the mint
shapes with short mint lid marks on the preserved dark faceplate.

## Playback conventions

* `behavior: "loop"` GIFs carry a NETSCAPE loop count of 0 (repeat forever);
  one-shots have **no** loop block (play once in the GIF itself).
* Ordinary one-shots start and finish on the neutral pose so an app can return
  straight to idle. `power-down` ends and `wake-up` starts on the same
  **resting** pose — frame-identical (verified).
* Preview: still thumbnails by default, per-card Play/Replay, 48 px and 96 px
  sizes (exact 1/4 and 1/2 of the 128x192 canvas), light/dark stage backgrounds,
  and a dedicated **power-down → wake-up** transition player.
