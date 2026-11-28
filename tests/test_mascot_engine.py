"""Static contract tests for the mascot sprite player and behaviour engine.

mascot.js and retro.css run in the browser, so these tests read them as
text (the style of tests/test_crt_speech_bubble.py) and assert the
behaviours docs/MASCOTS.md sections 3, 5 and 6 require: per-frame timing,
reduced motion, tab-hidden pausing, session greeting and chatter state,
the six priority levels, and the temporary legacy state adapter.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'
MASCOT_JS = ROOT / 'src' / 'static' / 'js' / 'mascot.js'
RETRO_CSS = ROOT / 'src' / 'static' / 'css' / 'retro.css'
MASCOT_TEMPLATE = ROOT / 'src' / 'templates' / '_mascot.html'
LESSON_DECK = ROOT / 'src' / 'templates' / 'lesson_deck.html'


def _read(path):
    return path.read_text(encoding='utf-8')


def test_per_frame_durations_drive_the_player():
    """Every frame must hold its own manifest duration. The retired CSS
    keyframe player dropped each animation's final frame and held the
    second-to-last twice as long; the JS player fixes both."""
    js = _read(MASCOT_JS)
    css = _read(RETRO_CSS)
    assert 'steps(' not in js, 'mascot.js must not do CSS steps() timing'
    assert not re.search(r'@keyframes\s+mascot-', css), (
        'retro.css must not carry per-state mascot keyframes'
    )
    block = re.search(r'#mascot\s*\{[^}]*\}', css, re.S)
    assert block, '#mascot CSS block not found'
    assert 'steps(' not in block.group(0), (
        'the mascot box must not animate via CSS timing functions'
    )
    # Frames advance on timers fed by the manifest's per-frame durations.
    assert re.search(r'frames\s*\[', js), (
        'the player must step through the manifest duration list'
    )
    assert 'setTimeout' in js
    assert 'background-position' in js or 'backgroundPosition' in js


def test_reduced_motion_shows_the_still_frame():
    """prefers-reduced-motion: reduce shows still.png and never
    animates; bubble text appears instantly (docs/MASCOTS.md §3)."""
    js = _read(MASCOT_JS)
    assert 'prefers-reduced-motion' in js
    # The player and the typewriter both consult the shared check
    # (definition + two call sites).
    assert js.count('_prefersReducedMotion(') >= 3, (
        'both the sprite player and the typewriter must honour '
        'prefers-reduced-motion'
    )


def test_player_pauses_when_the_tab_is_hidden():
    """Animations pause on document.hidden and resume without catch-up."""
    js = _read(MASCOT_JS)
    assert 'document.hidden' in js
    assert 'visibilitychange' in js


def test_session_greeting_flag_and_chatter_timestamp():
    """hello plays once per browser session and the chatter gap carries
    across pages via sessionStorage (docs/MASCOTS.md sections 5-6)."""
    js = _read(MASCOT_JS)
    assert js.count('sessionStorage') >= 2
    keys = set(re.findall(r"'(mascot_[a-z_]+)'", js))
    assert 'mascot_greeted' in keys, 'once-per-session greeting flag missing'
    assert 'mascot_last_line_at' in keys, 'chatter timestamp missing'
    # Each backing key is written and read again (definition + 2 uses):
    # the timestamp when any line shows and when the gap is computed, the
    # flag before the greeting is played.
    assert js.count('LAST_LINE_KEY') >= 3
    assert js.count('GREETED_KEY') >= 3


def test_no_fifteen_second_chatter_interval():
    """The old 15 s setInterval chatter is gone; all timing is chained
    timers off the configured gap."""
    js = _read(MASCOT_JS)
    assert 'setInterval' not in js, 'chatter must not run on an interval'
    assert '15000' not in js


def test_chatter_and_click_talk_respect_progress():
    """While a long job runs, chatter and click-talk are suppressed but
    clicks still get a reaction (docs/MASCOTS.md section 5)."""
    js = _read(MASCOT_JS)
    chatter = js[js.index('Chatter (docs/MASCOTS.md section 5)'):]
    chatter = chatter[:chatter.index('Session greeting')]
    assert '_progressActive' in chatter
    clicks = js[js.index('Hover and clicks'):]
    clicks = clicks[:clicks.index('Sleep (docs')]
    assert '_progressActive' in clicks
    assert 'reaction' in clicks


def test_behaviour_priorities_match_mascots_doc():
    """The six priority levels of docs/MASCOTS.md section 6, in order."""
    js = _read(MASCOT_JS)
    levels = re.findall(r'PRIO_(ERROR|EVENT|CLICK|HOVER|IDLE|BASE)\s*=\s*(\d+)',
                        js)
    assert [name for name, _ in levels] == [
        'ERROR', 'EVENT', 'CLICK', 'HOVER', 'IDLE', 'BASE',
    ], 'all six priorities must exist in the spec order'
    assert [int(n) for _, n in levels] == [1, 2, 3, 4, 5, 6]


def test_legacy_adapter_in_exactly_one_place():
    """progress.js, upload.js and lessons.html still send the old state
    names; one labelled table maps them until Task 5 replaces them."""
    hits = []
    for path in (list((SRC / 'static' / 'js').glob('*.js'))
                 + list((SRC / 'templates').glob('*.html'))):
        if 'LEGACY: removed in Task 5' in _read(path):
            hits.append(path.name)
    assert hits == ['mascot.js'], (
        f'legacy state adapter must live in mascot.js only, found in {hits}'
    )
    js = _read(MASCOT_JS)
    for legacy in ('idle', 'busy', 'busyB', 'busyC', 'happy', 'error',
                   'talk', 'wave'):
        assert f"'{legacy}'" in js, f'legacy state {legacy!r} no longer mapped'


def test_mascot_box_is_sized_from_the_manifest():
    """No fixed box size anywhere: the sprite box and the bubble
    placement derive from the active mascot's frame size (the three
    mascots have different frames; docs/MASCOTS.md section 3)."""
    tpl = _read(MASCOT_TEMPLATE)
    css = _read(RETRO_CSS)
    assert '--mascot-frame-w' in tpl and '--mascot-frame-h' in tpl
    assert 'var(--mascot-frame-w' in css
    bubble = re.search(r'#speech-bubble\s*\{[^}]*\}', css, re.S)
    assert bubble and 'var(--mascot-frame-h' in bubble.group(0), (
        'the bubble must sit relative to the mascot frame size so its '
        'tail keeps pointing at the mascot'
    )


def test_feet_stand_on_the_measured_floor():
    """The feet meet the footer's top border on every mascot page: both
    #mascot and #speech-bubble take their bottom from --mascot-floor
    (measured from .az-footer) minus the manifest ground offset, in the
    desktop rule and the phone rule alike. The bubble moves up by the
    same amount so its tail still points at the mascot."""
    css = _read(RETRO_CSS)
    tpl = _read(MASCOT_TEMPLATE)
    assert '--mascot-ground' in tpl, (
        'the manifest ground offset must reach CSS via _mascot.html'
    )
    mascot = re.search(r'#mascot\s*\{[^}]*\}', css).group(0)
    bubble = re.search(r'#speech-bubble\s*\{[^}]*\}', css).group(0)
    for block in (mascot, bubble):
        assert 'var(--mascot-floor' in block, (
            'desktop rule must position from the floor variable'
        )
        assert 'var(--mascot-ground' in block
    # The phone rules live in the media block that holds the second
    # #mascot rule.
    first = css.index('#mascot {')
    second = css.index('#mascot {', first + 1)
    phone = css[css.rindex('@media', 0, second):css.index('@media', second)]
    assert phone.count('var(--mascot-floor') >= 2, (
        'both phone rules must use the floor variable'
    )
    assert phone.count('var(--mascot-ground') >= 2


def test_mascot_js_measures_the_footer_floor():
    """mascot.js measures .az-footer's height and updates --mascot-floor
    at load and on resize, so no layout number is hard-coded."""
    js = _read(MASCOT_JS)
    assert 'az-footer' in js
    assert '--mascot-floor' in js
    assert "addEventListener('resize'" in js
    assert "addEventListener('load'" in js


def test_old_robot_is_gone():
    mascots = SRC / 'static' / 'images' / 'mascots'
    for state in ('busy', 'busyB', 'busyC', 'error', 'happy', 'idle',
                  'talk', 'wave'):
        assert not (mascots / state).exists(), (
            f'old robot state dir still present: {state}'
        )
    assert not (mascots / ('mascot-' + 'robot.png')).exists()
    assert not (mascots / ('mascot-' + 'robot-static.png')).exists()
    assert not (ROOT / ('generate_mascot' + '_anim.py')).exists()
    assert not (ROOT / 'tests' / ('test_mascot' + '_anim.py')).exists()


def test_nothing_references_the_old_robot():
    """No source or test file may reference the deleted robot. The
    needles are split so this file does not match itself."""
    needles = [
        'mascot-' + 'robot',
        'generate_mascot' + '_anim',
        'mascot-' + 'state-',
        'data-' + 'fallback-src',
        'robot-' + 'mascot',
    ]
    self_path = Path(__file__).resolve()
    scanned = 0
    for base in (SRC, ROOT / 'tests'):
        for path in base.rglob('*'):
            if not path.is_file() or path.resolve() == self_path:
                continue
            if path.suffix not in ('.py', '.js', '.css', '.html', '.md',
                                   '.json', '.yml'):
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            scanned += 1
            for needle in needles:
                assert needle not in text, f'{path}: still references {needle}'
    assert scanned > 10, 'sanity: the scan must actually cover the tree'


def test_lesson_deck_mascot_is_a_quiet_no_op():
    """lesson_deck.html loads mascot.js without the mascot markup; the
    script must exit quietly there."""
    deck = _read(LESSON_DECK)
    assert 'js/mascot.js' in deck
    assert '_mascot.html' not in deck
    js = _read(MASCOT_JS)
    assert "getElementById('mascot')" in js
    assert "getElementById('mascot-config')" in js
