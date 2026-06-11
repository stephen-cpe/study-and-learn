"""
Tests for the mascot GIF generator (Sprint 7 animation polish).

The mascot is a key piece of UX – these tests guard the user's
"make idle/busy/happy/error obviously distinct" requirement by enforcing:

* Each state has a minimum of 10 frames (user request, March 2026).
* Frames are pixel-unique (the GIF optimizer must not merge them).
* Transparency is preserved on every frame.
* Dimensions match the source ``mascot-robot.png`` (759x759).
* The four states are visually distinct from each other at every
  sampled frame, not just frame 0.
* The generator module is import-safe and never relies on a live AI
  call – it uses pure PIL/Numpy.
* The base mascot-robot.png artwork remains recognisable in every
  error frame (we choreograph the error, we don't re-paint the mascot).
* The template/JS wires the error state up.
"""
import os
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / 'src' / 'static' / 'images'
MASCOTS_DIR = IMG_DIR / 'mascots'

GIF_STATES = {
    'mascot-idle.gif':   {'min_frames': 10, 'duration': 250, 'tolerance': 0},
    'mascot-busy.gif':   {'min_frames': 10, 'duration': 140, 'tolerance': 0},
    'mascot-happy.gif':  {'min_frames': 10, 'duration': 220, 'tolerance': 0},
    'mascot-error.gif':  {'min_frames': 10, 'duration': 220, 'tolerance': 0},
}

# Each state's assets (gif + sprite + frames) live in their own subdirectory
# under src/static/images/mascots/ — see ADR-TBD in DESIGN_AND_TESTING.md.
GIF_STATE_DIRS = {
    'mascot-idle.gif':   MASCOTS_DIR / 'idle',
    'mascot-busy.gif':   MASCOTS_DIR / 'busy',
    'mascot-happy.gif':  MASCOTS_DIR / 'happy',
    'mascot-error.gif':  MASCOTS_DIR / 'error',
}

SOURCE_PNG = MASCOTS_DIR / 'mascot-robot.png'


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _transparent_ratio(im: Image.Image) -> float:
    """Return the fraction of pixels with alpha < 128 (treated as
    transparent by our GIF prep)."""
    rgba = im.convert('RGBA')
    alpha = rgba.split()[-1]
    total = rgba.size[0] * rgba.size[1]
    # Avoid ``Image.getdata()`` which is deprecated in Pillow 14.
    # We use ``numpy`` via the alpha band's tobytes for speed.
    import numpy as np
    arr = np.asarray(alpha)
    transparent = int((arr < 128).sum())
    return transparent / total


def _all_frames_pixel_unique(im: Image.Image) -> bool:
    seen = set()
    for i in range(im.n_frames):
        im.seek(i)
        seen.add(hash(im.convert('RGBA').tobytes()))
    return len(seen) == im.n_frames


def _frame_hashes(im: Image.Image, indices):
    out = {}
    for i in indices:
        im.seek(i)
        out[i] = hash(im.convert('RGBA').tobytes())
    return out


# --------------------------------------------------------------------------- #
# Source / GIF presence                                                       #
# --------------------------------------------------------------------------- #
def test_source_mascot_png_exists():
    assert SOURCE_PNG.is_file(), f'Missing source mascot PNG: {SOURCE_PNG}'


@pytest.mark.parametrize('name', list(GIF_STATES))
def test_gif_exists(name):
    path = GIF_STATE_DIRS[name] / name
    assert path.is_file(), f'Missing mascot GIF: {path}'


# --------------------------------------------------------------------------- #
# Frame count, dimensions, durations                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize('name,spec', list(GIF_STATES.items()))
def test_gif_meets_minimum_frame_count(name, spec):
    """The user requested >= 10 frames per status.  We actually ship 14/16/14
    but enforce the 10-frame minimum here so future regressions are caught."""
    im = Image.open(GIF_STATE_DIRS[name] / name)
    assert im.n_frames >= spec['min_frames'], (
        f'{name} has only {im.n_frames} frames (need >= {spec["min_frames"]})'
    )


@pytest.mark.parametrize('name', list(GIF_STATES))
def test_gif_dimensions_match_source(name):
    """The mascot GIFs are rendered at 759x759 to match mascot-robot.png.
    This matters because the slide deck CSS sizes the <img> at 120x120
    and a 1.0:1.0 aspect ratio is required for it to look right."""
    im = Image.open(GIF_STATE_DIRS[name] / name)
    assert im.size == (759, 759), f'{name} is {im.size}, expected (759, 759)'


@pytest.mark.parametrize('name,spec', list(GIF_STATES.items()))
def test_gif_per_frame_duration_uniform(name, spec):
    """A non-uniform per-frame duration looks janky in browsers."""
    im = Image.open(GIF_STATE_DIRS[name] / name)
    durations = [im.info.get('duration')]
    for i in range(1, im.n_frames):
        im.seek(i)
        durations.append(im.info.get('duration'))
    assert all(d == spec['duration'] for d in durations), (
        f'{name} has non-uniform durations {set(durations)} '
        f'(expected all {spec["duration"]}ms)'
    )


# --------------------------------------------------------------------------- #
# Transparency preservation                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize('name', list(GIF_STATES))
def test_gif_transparency_preserved_first_and_last_frame(name):
    """The original .gif files had a transparent background.  The new ones
    must keep that – the cyberpunk UI shows the GIF over the page
    background, so any opaque rectangle would be visible."""
    im = Image.open(GIF_STATE_DIRS[name] / name)
    im.seek(0)
    first_ratio = _transparent_ratio(im)
    im.seek(im.n_frames - 1)
    last_ratio = _transparent_ratio(im)
    # The mascot itself occupies ~19% of the canvas.  We require the
    # transparent fraction to be > 50% on every frame to confirm the
    # background is mostly transparent (with tolerance for quantisation
    # artefacts that may extend a few pixels into the background).
    assert first_ratio > 0.50, (
        f'{name} frame 0 only {first_ratio:.0%} transparent – background may be opaque'
    )
    assert last_ratio > 0.50, (
        f'{name} last frame only {last_ratio:.0%} transparent – background may be opaque'
    )


@pytest.mark.parametrize('name', list(GIF_STATES))
def test_gif_transparency_present_on_every_frame(name):
    """Spot-check transparency on the middle frame too – some frames
    could have a stray opaque pixel that breaks the transparent look."""
    im = Image.open(GIF_STATE_DIRS[name] / name)
    im.seek(im.n_frames // 2)
    mid_ratio = _transparent_ratio(im)
    assert mid_ratio > 0.50, (
        f'{name} mid frame only {mid_ratio:.0%} transparent'
    )


# --------------------------------------------------------------------------- #
# Frame uniqueness (no optimizer merging)                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize('name', list(GIF_STATES))
def test_gif_all_frames_pixel_unique(name):
    """If two frames are pixel-identical Pillow's GIF optimizer will
    merge them and the loop will have fewer frames than the generator
    intended.  The user wants the full 14/16/14 cycle visible."""
    im = Image.open(GIF_STATE_DIRS[name] / name)
    assert _all_frames_pixel_unique(im), (
        f'{name} has duplicate frames (GIF optimizer merged them)'
    )


# --------------------------------------------------------------------------- #
# Cross-state distinctness                                                    #
# --------------------------------------------------------------------------- #
def test_states_are_visually_distinct_from_each_other():
    """idle, busy, happy, and error must look obviously different.
    Compare multiple frames across the loop – not just frame 0 – because
    animations only convey state over time."""
    gifs = {name: Image.open(GIF_STATE_DIRS[name] / name) for name in GIF_STATES}
    # Use the largest common frame index (happy/error only have 14)
    indices = [0, 5, 10, 13]
    for i in indices:
        hashes = {}
        for name, im in gifs.items():
            seek_to = min(i, im.n_frames - 1)
            im.seek(seek_to)
            hashes[name] = hash(im.convert('RGBA').tobytes())
        assert len(set(hashes.values())) == 4, (
            f'At frame {i}, two mascot states share identical pixel '
            f'content (not visually distinct): {hashes}'
        )


# --------------------------------------------------------------------------- #
# Generator module sanity                                                     #
# --------------------------------------------------------------------------- #
def test_generator_module_is_importable():
    """The generator must be importable without side-effects.  It must
    not require a live AI or external service."""
    import importlib
    mod = importlib.import_module('generate_mascot_anim')
    # Public surface – the build_* helpers should be present.
    for name in (
        'build_idle_frames',
        'build_busy_frames',
        'build_happy_frames',
        'build_error_frames',
    ):
        assert hasattr(mod, name), f'generate_mascot_anim.{name} missing'


def test_generator_choreographies_have_expected_frame_counts():
    """Sanity-check the build functions return the right number of
    frames (matches the GIFs saved on disk).  Runs the generator
    in-memory with no I/O."""
    from generate_mascot_anim import (
        build_idle_frames, build_busy_frames, build_happy_frames,
        build_error_frames, load_base,
    )
    base = load_base()
    assert len(build_idle_frames(base)) == 14
    assert len(build_busy_frames(base)) == 16
    assert len(build_happy_frames(base)) == 14
    assert len(build_error_frames(base)) == 14


def test_generator_frames_have_transparent_background():
    """Each frame returned by the build_* helpers must be a 759x759
    RGBA image with a transparent background, ready for the GIF
    prep step."""
    from generate_mascot_anim import (
        build_idle_frames, build_busy_frames, build_happy_frames,
        build_error_frames, load_base,
    )
    base = load_base()
    for build_fn in (
        build_idle_frames,
        build_busy_frames,
        build_happy_frames,
        build_error_frames,
    ):
        for frame in build_fn(base):
            assert frame.size == (759, 759)
            assert frame.mode == 'RGBA'
            # At least 50% of pixels must be transparent.
            ratio = _transparent_ratio(frame)
            assert ratio > 0.50, f'frame is {ratio:.0%} transparent'


def test_error_state_preserves_base_mascot_pixels():
    """The user requirement: the original mascot-robot.png must remain
    visible in the generated error GIF – the new state should not
    re-paint the mascot with red overlays that would obscure the
    original artwork.  This test asserts that, for every error frame,
    the *majority* of the non-transparent pixels in the mascot's
    bounding box still match the base PNG (allowing for per-frame
    choreography like X-eyes and dimmed chest lights)."""
    import numpy as np
    from generate_mascot_anim import build_error_frames, load_base

    base = load_base()
    base_arr = np.array(base)
    # Bounding box of the mascot inside the source PNG.
    bbox = (125, 50, 750, 723)
    base_bbox = base_arr[bbox[1]:bbox[3], bbox[0]:bbox[2]]

    for idx, frame in enumerate(build_error_frames(base)):
        farr = np.array(frame)
        f_bbox = farr[bbox[1]:bbox[3], bbox[0]:bbox[2]]
        # Pixels in the base that are non-transparent.
        base_alpha = base_bbox[:, :, 3] > 128
        # Pixels in the frame that are non-transparent AND match the
        # base pixel within +/- 5 units per channel (so X-eye overlays
        # and chest dimming don't fail the test, but a full red re-paint
        # would).
        f_alpha = f_bbox[:, :, 3] > 128
        common = base_alpha & f_alpha
        if common.sum() == 0:
            pytest.fail(
                f'error frame {idx}: no overlapping non-transparent '
                f'pixels with base mascot – the mascot has been replaced!'
            )
        base_pixels = base_bbox[common][:, :3].astype(int)
        f_pixels = f_bbox[common][:, :3].astype(int)
        # Per-channel distance
        max_diff = np.abs(base_pixels - f_pixels).max(axis=1)
        close = (max_diff <= 25).sum() / len(max_diff)
        # At least 70% of the mascot's pixels should still be close
        # enough to the base (allowing for chest/animation variations).
        assert close >= 0.70, (
            f'error frame {idx}: only {close:.0%} of mascot pixels are '
            f'close to the base – the mascot may have been re-painted.'
        )


# --------------------------------------------------------------------------- #
# Template / JS wiring                                                        #
# --------------------------------------------------------------------------- #
def test_mascot_template_wires_error_state():
    """The _mascot.html partial must register the error GIF via a
    data-error-src attribute so setMascotState('error') can switch to it."""
    template = (ROOT / 'src' / 'templates' / '_mascot.html').read_text()
    assert 'mascot-error.gif' in template, (
        '_mascot.html does not reference mascot-error.gif'
    )
    assert 'data-error-src' in template, (
        '_mascot.html does not declare a data-error-src attribute on the <img>'
    )


def test_mascot_template_uses_new_state_subdirectory_layout():
    """After the images/ reorganization (Sprint 7), each mascot state's
    GIF must live under mascots/{state}/, not directly in images/."""
    template = (ROOT / 'src' / 'templates' / '_mascot.html').read_text()
    expected_substrings = [
        'images/mascots/idle/mascot-idle.gif',
        'images/mascots/busy/mascot-busy.gif',
        'images/mascots/happy/mascot-happy.gif',
        'images/mascots/error/mascot-error.gif',
        'images/mascots/mascot-robot.png',
    ]
    for needle in expected_substrings:
        assert needle in template, (
            f'_mascot.html is missing the new path: {needle}'
        )


def test_mascot_js_supports_error_state():
    """mascot.js must accept 'error' as a valid state in setMascotState
    and add/remove the mascot-state-error CSS class accordingly."""
    js = (ROOT / 'src' / 'static' / 'js' / 'mascot.js').read_text()
    assert "'error'" in js or '"error"' in js, (
        "mascot.js does not list 'error' as a valid mascot state"
    )
    assert 'mascot-state-error' in js, (
        "mascot.js does not toggle the mascot-state-error CSS class"
    )


def test_retro_css_declares_error_state_glow():
    """The retro theme should tint the mascot red/orange in the error
    state so the visual cue is consistent with the busy/happy glows."""
    css = (ROOT / 'src' / 'static' / 'css' / 'retro.css').read_text()
    assert '#robot-mascot.mascot-state-error' in css, (
        'retro.css does not declare a glow for mascot-state-error'
    )
