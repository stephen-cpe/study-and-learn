# Mascot generators (`tools/mascots/`)

This folder holds mimo's animation generators and the approved base art for
**Raster**, **Pip** and **Trace**, kept so the animations can be regenerated and
extended (see `docs/MASCOTS.md`). Nothing here runs in the web app: the browser
only ever sees the built assets under `src/static/images/mascots/`.

## What's here

- `raster-animations/`, `pip-animations/`, `trace-animations/` — one animation
  pack per mascot. Each pack holds `frames/<animation>/NNN.png` (transparent
  RGBA frames), `gifs/`, `manifest.json`, `preview.html` (an offline gallery you
  can double-click), `README.md` (the pack's own manual — read it before
  editing anything) and `source/` (the generator scripts, editable layers,
  poses and diagnostic images). Pip also keeps `baseline/` and `poses/`.
- `raster.png`, `pip.png`, `trace.png` — the approved base art each pack was
  generated from. The generator scripts find their base art through relative
  paths such as `../pip.png`, so keep these files in this exact layout.
- `build_web_assets.py` — turns the packs into the web assets the app serves.
- this README.

The packs were copied verbatim from mimo's delivery folder. Only `__pycache__/`
was left out; everything else (GIFs, diagnostics, baselines) is preserved.

## Regenerating a pack

Run from the repository root. All three packs need nothing but Python 3,
Pillow and numpy. The commands are the ones from each pack's README.

### Raster

```powershell
python tools\mascots\raster-animations\source\make_parts.py
python tools\mascots\raster-animations\source\make_poses.py
python tools\mascots\raster-animations\source\render.py
python tools\mascots\raster-animations\source\verify.py
```

One animation only: `python tools\mascots\raster-animations\source\render.py hello`.

Known gap: `source/compare_reference.py` renders a comparison against the old
Study Robot under `../references/`, which is deliberately not part of this
repo. The script is left exactly as mimo delivered it and will not run here.

### Pip

```powershell
python tools\mascots\pip-animations\source\layers.py
python tools\mascots\pip-animations\source\build.py
python tools\mascots\pip-animations\source\verify.py
```

One or more animations: `python tools\mascots\pip-animations\source\build.py idle-blink`.

### Trace

```powershell
python tools\mascots\trace-animations\source\extract.py
python tools\mascots\trace-animations\source\segment.py
python tools\mascots\trace-animations\source\build.py
python tools\mascots\trace-animations\source\verify.py
```

One or more animations: `python tools\mascots\trace-animations\source\build.py idle-blink`.
`build.py` alone is enough when only timings or choreography changed.

## Rebuilding the web assets

Whenever a pack changes (or you switch a scaling method), run from the
repository root:

```powershell
python tools/mascots/build_web_assets.py
```

It reads `tools/mascots/<id>-animations/` and rewrites
`src/static/images/mascots/<id>/` for all three mascots. Per mascot that is one
horizontal sprite sheet per animation (`<animation>.png`), `still.png` (the
neutral frame for reduced motion and fallbacks), `preview-idle.gif` (loops,
for the Settings picker), `preview-hello.gif` (plays once) and `manifest.json`
in one normalized shape for all three.

What the build guarantees:

- **Uniform body height** (90 px, Raster's native size) so the three mascots
  share one baseline: `docs/MASCOTS.md` section 3.
- **No clipping:** every frame of a mascot shares one frame size, cropped to
  the union of all frames' alpha bounding boxes plus a 2 px margin.
- **Hold frames stay holds:** one PNG per unique frame, with the hold times in
  the manifest — nothing is expanded into duplicate frames.
- **Determinism:** running the build twice produces byte-identical output.
  `--out <dir>` writes somewhere else instead (used by the tests).

Scaling is a per-mascot setting at the top of `build_web_assets.py`:

```python
SCALING = {'raster': None, 'pip': 'nearest', 'trace': 'lanczos'}
```

`None` keeps the source pixels untouched (Raster is already 90 px and must stay
pixel-perfect), `nearest` samples whole source pixels (keeps Pip's 12-colour
palette exact), `box`/`lanczos` resample with premultiplied alpha and then
threshold the alpha so edges stay hard. Switching a mascot later is a one-line
change here plus a rebuild.

After rebuilding, run the tests: `tests/test_mascot_assets.py` checks the built
assets against the pack manifests and rebuilds them to prove the result is
reproducible.
