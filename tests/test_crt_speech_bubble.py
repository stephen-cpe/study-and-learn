"""Tests for the CRT-styled mascot speech bubble and its typewriter animation.

These are static-asset tests: they assert the markup / CSS / JS exist with
the right contracts so that regressions are caught even though the bubble
is rendered in the browser. The tests do not need a running Flask app.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_CSS = ROOT / 'src' / 'static' / 'css' / 'fonts.css'
RETRO_CSS = ROOT / 'src' / 'static' / 'css' / 'retro.css'
MASCOT_JS = ROOT / 'src' / 'static' / 'js' / 'mascot.js'
PROGRESS_JS = ROOT / 'src' / 'static' / 'js' / 'progress.js'
MASCOT_TEMPLATE = ROOT / 'src' / 'templates' / '_mascot.html'
FONT_DIR = ROOT / 'src' / 'static' / 'fonts' / 'pressstart2p'


def _read(path):
    return path.read_text(encoding='utf-8')


def test_pressstart2p_font_is_vendored():
    """The font must be vendored under src/static/fonts/pressstart2p/."""
    assert FONT_DIR.is_dir(), f'Missing font dir: {FONT_DIR}'
    files = list(FONT_DIR.glob('*.ttf')) + list(FONT_DIR.glob('*.otf'))
    assert files, 'No TTF/OTF font found under src/static/fonts/pressstart2p/'


def test_pressstart2p_font_face_declared():
    css = _read(FONTS_CSS)
    assert '@font-face' in css
    assert 'PressStart2P' in css
    assert 'pressstart2p/PressStart2P-Regular.ttf' in css, (
        '@font-face for PressStart2P must point to the vendored font file'
    )


def test_speech_bubble_is_crt_styled():
    css = _read(RETRO_CSS)
    # Find the *first* #speech-bubble block (it has the geometry/palette);
    # a second block (display: flex) may follow for layout overrides.
    block_match = re.search(r'#speech-bubble\s*\{[^}]*\}', css, re.S)
    assert block_match, '#speech-bubble CSS block not found'
    block = block_match.group(0)
    assert 'aspect-ratio: 4 / 3' in block, (
        'CRT bubble must use aspect-ratio: 4 / 3 (4:3 monitor shape)'
    )
    assert 'PressStart2P' in block, (
        'CRT bubble must use the PressStart2P pixel font'
    )
    assert '#000000' in block or 'var(--crt-bg)' in block, (
        'CRT bubble must have a black background'
    )
    assert '33ff66' in block.lower() or 'var(--crt-fg)' in block, (
        'CRT bubble must use green foreground text'
    )
    assert 'repeating-linear-gradient' in css, (
        'CRT effect requires scanlines (repeating-linear-gradient)'
    )


def test_speech_bubble_is_reduced_30_percent():
    """User requirement: base width must be reduced by ~30% from the original
    288px CRT prototype (i.e. ≈ 200px). Font-size (9px) must stay unchanged."""
    css = _read(RETRO_CSS)
    block_match = re.search(r'#speech-bubble\s*\{[^}]*\}', css, re.S)
    assert block_match
    block = block_match.group(0)
    m = re.search(r'width:\s*(\d+(?:\.\d+)?)px', block)
    assert m, '#speech-bubble must declare width in px'
    width = float(m.group(1))
    # 30% smaller than 288 ≈ 200. Accept 190–205 to be tolerant of tweaks.
    assert 190 <= width <= 205, (
        f'Expected ~200px width (~30% smaller than 288), got {width}px'
    )
    # Font size must NOT be changed (9px).
    fm = re.search(r'font-size:\s*(\d+(?:\.\d+)?)px', block)
    assert fm
    assert float(fm.group(1)) == 9, f'font-size must remain 9px, got {fm.group(1)}'


def test_speech_bubble_has_inner_text_margin():
    """User requirement: text must not stick to the screen edge — the
    #bubble-text element must have non-zero padding."""
    css = _read(RETRO_CSS)
    m = re.search(r'#bubble-text\s*\{[^}]*\}', css, re.S)
    assert m, '#bubble-text CSS block not found'
    block = m.group(0)
    pm = re.search(r'padding:\s*([^;]+);', block)
    assert pm, '#bubble-text must declare padding so text does not stick to the screen edge'
    parts = pm.group(1).split()
    nums = [float(p.rstrip('px')) for p in parts if p.endswith('px')]
    assert any(n > 0 for n in nums), 'padding must be non-zero on at least one side'


def test_speech_bubble_caps_text_at_4_lines():
    """User requirement: the text area must visually cap at 4 lines so the
    progress bar at the bottom is never pushed off the CRT screen."""
    css = _read(RETRO_CSS)
    m = re.search(r'#bubble-text\s*\{[^}]*\}', css, re.S)
    assert m
    block = m.group(0)
    assert 'max-height' in block, '#bubble-text must cap its height'
    assert 'overflow: hidden' in block, '#bubble-text must clip overflow at 4 lines'
    # The cap is expressed in line-height units. Accept any of:
    #   4 * line-height, 4em, 5.6em, 4lh, calc(... * 4), calc(... * N), etc.
    cap_m = re.search(r'max-height:\s*([^;]+);', block)
    assert cap_m
    cap = cap_m.group(1)
    four_line_patterns = [
        r'4\s*\*\s*var\(--crt-text-line\)',
        r'4em',
        r'4lh',
        r'5\.6em',
        r'57\.6px',
        r'calc\(var\(--crt-text-line\)\s*\*\s*4',
        r'calc\(var\(--crt-text-line\)\s*\*\s*var\(--crt-text-max-lines\)\)',
        r'4\b.*\*',
    ]
    assert any(re.search(p, cap) for p in four_line_patterns), (
        f'max-height ({cap}) must represent a 4-line cap'
    )


def test_progress_bar_pinned_to_bottom_of_crt():
    """The progress bar must be the flex item pinned at the bottom of the
    flex column so it never overlaps the typewriter text above it."""
    css = _read(RETRO_CSS)
    assert 'display: flex' in css or 'display:flex' in css, (
        '#speech-bubble must be a flex column so the progress bar pins to the bottom'
    )
    bp = re.search(r'\.bubble-progress\s*\{[^}]*\}', css, re.S)
    assert bp, '.bubble-progress block not found'
    assert 'flex: 0 0 auto' in bp.group(0), (
        '.bubble-progress must use flex: 0 0 auto so it stays pinned to the bottom'
    )


def test_speech_bubble_has_scanlines_and_screen_surface():
    """The bubble must layer a "screen" surface + scanlines via ::before / ::after."""
    css = _read(RETRO_CSS)
    assert re.search(r'#speech-bubble::before\s*\{', css), (
        'CRT bubble must use ::before to draw the inner screen surface'
    )
    assert re.search(r'#speech-bubble::after\s*\{', css), (
        'CRT bubble must use ::after for scanline overlay'
    )


def test_caret_class_is_defined():
    css = _read(RETRO_CSS)
    assert '.bubble-caret' in css, 'A .bubble-caret class must be defined for the typing caret'
    assert 'bubble-caret-blink' in css, 'A blink animation for the caret must be defined'


def test_speech_bubble_template_contains_tail_and_default_text():
    tpl = _read(MASCOT_TEMPLATE)
    assert 'bubble-tail' in tpl, '_mascot.html must include a bubble-tail element'
    assert 'bubble-text' in tpl
    assert 'id="speech-bubble"' in tpl, 'Template must declare the speech-bubble element'
    # Default text should be short and on-theme for the CRT bubble.
    default_match = re.search(r'id="bubble-text">([^<]+)</', tpl)
    assert default_match, 'Default bubble text not found'
    assert len(default_match.group(1).strip()) <= 30, (
        'Default bubble text should be short (CRT-friendly)'
    )


def test_mascot_js_typewriter_uses_fast_per_char_delay():
    js = _read(MASCOT_JS)
    # The "really quickly" feel = a small per-char delay.
    m = re.search(r'TYPEWRITER_CHAR_DELAY_MS\s*=\s*(\d+)', js)
    assert m, 'TYPEWRITER_CHAR_DELAY_MS constant missing in mascot.js'
    delay = int(m.group(1))
    assert 1 <= delay <= 40, f'Typewriter delay too slow for "really quickly" feel: {delay}ms'


def test_mascot_js_typewriter_appends_caret():
    js = _read(MASCOT_JS)
    assert 'bubble-caret' in js, 'mascot.js must inject the .bubble-caret element'
    assert 'aria-hidden' in js, 'Caret should be aria-hidden'


def test_mascot_messages_are_short_for_crt():
    """Idle/click messages must be short so they fit the 4:3 CRT frame."""
    js = _read(MASCOT_JS)
    m = re.search(r"var messages = \[(.*?)\];", js, re.S)
    assert m, 'messages array not found in mascot.js'
    body = m.group(1)
    items = re.findall(r"'([^']+)'", body)
    assert items, 'no message literals found'
    for line in items:
        assert len(line) <= 28, f'Idle mascot line too long for CRT bubble: {line!r}'


def test_progress_js_uses_bubble_typewriter_for_persistent_messages():
    js = _read(PROGRESS_JS)
    assert '_bubbleTypewrite' in js, (
        'progress.js must use window._bubbleTypewrite for setBubblePersistent '
        'so progress messages also stream onto the CRT.'
    )
    assert 'setBubblePersistent' in js


def test_mascot_init_exposes_typewriter_for_progress():
    js = _read(MASCOT_JS)
    assert 'window._bubbleTypewrite' in js, (
        'mascot.js must expose window._bubbleTypewrite so progress.js can reuse it'
    )


def test_old_long_mascot_messages_removed():
    """The old verbose messages must no longer appear in JS / template."""
    js = _read(MASCOT_JS)
    tpl = _read(MASCOT_TEMPLATE)
    stale = [
        "I\u2019m here to help you learn",
        "I'm here to help you learn",
        "you\u2019re smarter than you were 5 minutes ago",
        "you\u2019re about to become a superhero",
        "Whatever \"this\" is",
        "I use it to help you study",
    ]
    blob = js + '\n' + tpl
    for snippet in stale:
        assert snippet not in blob, f'Stale verbose mascot line still present: {snippet!r}'
