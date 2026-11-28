"""Tests for the generated mascot web assets.

These guard the output of tools/mascots/build_web_assets.py in
src/static/images/mascots/{raster,pip,trace}/: every source animation ships,
sheets match their manifest entries, all three mascots share the 90 px body
height from docs/MASCOTS.md section 3, and a rebuild reproduces the committed
pictures. The rebuild compares decoded pixels rather than file bytes, so a
Pillow encoder change cannot fail these tests while the pictures are identical.
"""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / 'src' / 'static' / 'images' / 'mascots'
PACKS_DIR = ROOT / 'tools' / 'mascots'
BUILD_SCRIPT = PACKS_DIR / 'build_web_assets.py'
MASCOTS = ('raster', 'pip', 'trace')


def _web_manifest(mid):
    return json.loads((WEB_DIR / mid / 'manifest.json').read_text(encoding='utf-8'))


def _source_names(mid):
    manifest = PACKS_DIR / (mid + '-animations') / 'manifest.json'
    man = json.loads(manifest.read_text(encoding='utf-8'))
    return {entry['name'] for entry in man['animations']}


def test_every_source_animation_ships():
    """Nothing was dropped: web manifest == pack manifest, exactly 32 each."""
    for mid in MASCOTS:
        web = _web_manifest(mid)['animations']
        assert set(web) == _source_names(mid), f'{mid}: web and source animation sets differ'
        assert len(web) == 32, f'{mid}: expected 32 animations, got {len(web)}'


def test_mascot_specific_animations():
    """The personality-defining animations exist (docs/MASCOTS.md section 9)."""
    raster = _web_manifest('raster')['animations']
    pip = _web_manifest('pip')['animations']
    trace = _web_manifest('trace')['animations']
    assert {'encourage', 'idle-antenna-settle'} <= set(raster)
    assert {'idle-tail-sway', 'relieved'} <= set(pip)
    assert {'writing', 'idle-sway', 'relieved'} <= set(trace)
    assert 'speaking' not in trace, 'Trace talks with writing, never speaking'


def test_sheets_match_manifest():
    """Every sheet is as wide as its frame list and agrees with manifest.json."""
    for mid in MASCOTS:
        man = _web_manifest(mid)
        frame_w, frame_h = man['frame_width'], man['frame_height']
        for name, anim in man['animations'].items():
            sheet = WEB_DIR / mid / anim['sheet']
            assert sheet.is_file(), f'missing sheet {mid}/{name}'
            count = len(anim['frames'])
            with Image.open(sheet) as img:
                assert img.size == (count * frame_w, frame_h), (
                    f'{mid}/{name}: sheet {img.size} does not fit '
                    f'{count} frames of {frame_w}x{frame_h}'
                )
            assert all(d > 0 for d in anim['frames']), f'{mid}/{name}: non-positive duration'
            assert anim['total_ms'] == sum(anim['frames']), (
                f'{mid}/{name}: total_ms is not the sum of the per-frame durations'
            )
            assert isinstance(anim['loop'], bool), f'{mid}/{name}: loop must be a bool'


def test_uniform_body_height():
    """All three mascots render at one visible height: 90 px within 1 px."""
    for mid in MASCOTS:
        body = _web_manifest(mid)['body_height']
        assert abs(body - 90) <= 1, f'{mid}: body_height {body}px is off the 90 px target'


def test_auxiliary_files_exist():
    """still.png and both Settings-picker previews exist for every mascot."""
    for mid in MASCOTS:
        for name in ('still.png', 'preview-idle.gif', 'preview-hello.gif'):
            assert (WEB_DIR / mid / name).is_file(), f'missing {mid}/{name}'


def test_preview_gif_play_modes():
    """The picker idle loops forever; hello plays once (docs/MASCOTS.md section 9)."""
    for mid in MASCOTS:
        idle = Image.open(WEB_DIR / mid / 'preview-idle.gif')
        hello = Image.open(WEB_DIR / mid / 'preview-hello.gif')
        assert idle.info.get('loop') == 0, f'{mid}: preview-idle.gif must loop'
        assert 'loop' not in hello.info, f'{mid}: preview-hello.gif must play once'


def _gif_frames(path):
    img = Image.open(path)
    frames = []
    for i in range(getattr(img, 'n_frames', 1)):
        img.seek(i)
        frames.append((img.info.get('duration'), img.convert('RGBA').tobytes()))
    return frames


def _assert_same_pictures(a, b):
    if a.name == 'manifest.json':
        left = json.loads(a.read_text(encoding='utf-8'))
        right = json.loads(b.read_text(encoding='utf-8'))
        assert left == right, 'manifest.json differs after rebuild'
    elif a.suffix == '.gif':
        left, right = _gif_frames(a), _gif_frames(b)
        assert len(left) == len(right), f'{a.name}: frame count differs after rebuild'
        assert [f[0] for f in left] == [f[0] for f in right], (
            f'{a.name}: per-frame durations differ after rebuild'
        )
        assert [f[1] for f in left] == [f[1] for f in right], (
            f'{a.name}: decoded pixels differ after rebuild'
        )
    else:
        with Image.open(a) as left, Image.open(b) as right:
            assert left.size == right.size, f'{a.name}: size differs after rebuild'
            assert left.convert('RGBA').tobytes() == right.convert('RGBA').tobytes(), (
                f'{a.name}: pixels differ after rebuild'
            )


def test_rebuild_reproduces_the_committed_pictures():
    """A fresh build into a temp dir matches the committed assets picture by picture.

    File bytes may legitimately differ across Pillow releases (encoder
    changes); the decoded pictures may not.
    """
    with TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), '--out', tmp],
            check=True,
            capture_output=True,
        )
        for mid in MASCOTS:
            committed = sorted(p.name for p in (WEB_DIR / mid).iterdir())
            rebuilt = sorted(p.name for p in (Path(tmp) / mid).iterdir())
            assert committed == rebuilt, f'{mid}: rebuilt file set differs'
            for name in committed:
                _assert_same_pictures(WEB_DIR / mid / name, Path(tmp) / mid / name)
