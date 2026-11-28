# Trace animation pack

32 transparent animated GIFs of **Trace**, the Azthreus assistant mascot, plus
editable PNG frames and the source that generates them from `../trace.png`.

- **Sprite source:** `trace.png` (untouched) - 1254 x 1254 RGBA, pixel-*style*
  art with soft edges and generation noise.
- **Measured pixel grid:** stair-step contours fit blocks of `sx = 9.83 px`,
  `sy = 9.73 px` (Fourier lattice fit on the alpha/colour edges - see
  `source/lattice_alpha.py`).  That is a ~128-cell grid, *not* 64 x 64.  The
  true visible bounds are `(355, 78, 860, 1196)` = 505 x 1118 px ≈ 51 x 115
  cells of content (a stray alpha-1 haze inflates the naive bbox).
- **Working grid:** 128 x 128 cells, one colour per cell (median of the source
  block, snapped to the 28-colour source palette).
- **Canvas:** 140 x 140 cells, identical for every animation.  Content sits at
  x 44..94, y 12..126 with >= 10 cells of margin for the largest movement
  (`celebrate`).  **Anchor** (pivot for leans, nods, squash/stretch):
  bottom of the outer loop = `(66, 132)`.
- Movement is whole-pixel on the working grid; scaling is nearest-neighbor.
  Background and the loop openings stay transparent.

## Layout

```
trace-animations/
  gifs/                 32 transparent animated GIFs (the filenames from the brief)
  frames/<name>/        numbered transparent PNG frames (00.png, 01.png, ...)
                        one PNG per *unique* displayed frame; durations in manifest.json
  source/
    layers/             reusable layers/masks at canvas resolution:
                        behind.png (body + wire continued behind the eyes),
                        body.png, eye_L/R.png (eye graphic incl. rim),
                        white_L/R.png (sclera with the pupil footprint filled),
                        pupil_L/R.png (pupil + cross catchlight),
                        brow_L/R.png, led.png
    extract.py          trace.png -> working grid + palette  (grid.png, palette.json)
    segment.py          grid -> the layers above             (components.json)
    motions.py          rig + shared motions: BLINK_STEPS, gaze(), eyes(), brows(),
                        LED_STATES, lean()/squash()/hop()/move(), Pose, compositor
    build.py            the 32 choreographies + GIF/PNG export + manifest + preview.html
    verify.py           decodes every GIF and checks it against manifest.json
    contact_sheet.py    QA contact sheets at 2x / 96px / 48px
    analyze.py, lattice_fit.py, lattice_alpha.py, grid_detect.py, grid_test.py,
    steps.py, probe.py  measurement scripts (how the pixel grid was found)
  manifest.json         per-animation: name, category, gif path, loop/one-shot,
                        frame durations (ms), total duration, start/end pose
  preview.html          local gallery (open in any browser)
```

## Preview

Open `trace-animations/preview.html` in a browser (double-click it - no server
needed).  Thumbnails stay still; press **Play** / **Replay** on a card (or click
its preview) to run one motion.  **Dark background** toggles the stage colour;
each card shows 48 px and 96 px previews, exactly as delivered sizes.

## Regenerate the pack from trace.png

```
python trace-animations/source/extract.py     # trace.png -> grid.png + palette.json
python trace-animations/source/segment.py     # grid -> source/layers/*.png
python trace-animations/source/build.py       # layers -> gifs/, frames/, manifest.json, preview.html
python trace-animations/source/verify.py      # decode + check every GIF against the manifest
```

`build.py` alone is enough whenever only timings or choreography changed - it
rebuilds everything from the layers.  `trace.png` and the original file are
never modified.

## Adjust a motion

- **Shared movement** (blink shape, gaze range, brow lift, LED tones, lean/
  squash amounts): edit `source/motions.py`.  `BLINK_STEPS`, `LED_STATES` and
  the `Pose` helpers are the single places these live.
- **One animation's choreography**: edit its entry in `animations()` in
  `source/build.py` - each is a list of `(pose, duration_ms)` built from the
  shared blocks.  Durations may be any multiple of 10 ms (GIF resolution);
  identical consecutive frames are merged automatically and their durations
  summed, so holds cost one frame.
- Re-export (see below) and re-run `verify.py`.

## Export a single animation again

```
python trace-animations/source/build.py idle-blink
```

(Any number of names can be passed; without names it rebuilds all 32 and also
rewrites `manifest.json` and `preview.html`.)

## Notes on the rig

- **Layers.** The neutral pose reassembles from the layers to within 11 cells of
  the extraction - those are deliberate noise-speck cleanups along the rims
  (compare `source/compare.png`, original vs reconstruction).
- **Behind the eyes.** `behind.png` continues the wire bands for a few cells
  behind each eye rim (the inner-loop arm at the left eye, the descending wire
  at the right eye), so blinks and gaze shifts reveal plausible pixels instead
  of holes.  Where the source wire merely passes *above* an eye (the right
  eye's top arc), the gap stays transparent.
- **Blinks** are an upper-lid crop with a curved dark lid edge; the pupil is
  clipped to the remaining eye, so nothing ghosts.
- **Status light** is the tiny 2-cell teal square in the collar (true to the
  source).  States reuse existing source teals: `bright #07efe3`,
  `mid #039f90`, `dim #44777f`, `off #222632`, `on` = the source pattern.
- **Gaze range is asymmetric** because Trace's neutral curious glance already
  points up-right in the source (the pupils sit 1 cell from the eye's top-right
  rim).  `look-left` therefore travels further than `look-right`/`look-up`;
  those lead with the eye/brow offsets to keep the direction readable at 48 px.
- Loops repeat forever (NETSCAPE loop 0); one-shots intentionally *omit* the
  loop extension and play once - `verify.py` asserts both cases byte-level.
