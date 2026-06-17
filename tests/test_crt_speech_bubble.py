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


def test_speech_bubble_caps_text_at_5_lines():
    """User requirement: the text area must visually cap at 5 lines so the
    progress bar at the bottom is never pushed off the CRT screen.

    The 5-line CSS cap provides 4 full lines of text plus descender
    headroom, fixing the clipping that previously cut off the bottom
    halves of the last line in a 4-line message.
    """
    css = _read(RETRO_CSS)
    m = re.search(r'#bubble-text\s*\{[^}]*\}', css, re.S)
    assert m
    block = m.group(0)
    assert 'max-height' in block, '#bubble-text must cap its height'
    assert 'overflow: hidden' in block, '#bubble-text must clip overflow'
    # The cap is expressed in line-height units. Accept any of:
    #   5 * line-height, 5em, 7em, 5lh, 72px, calc(... * 5), etc.
    cap_m = re.search(r'max-height:\s*([^;]+);', block)
    assert cap_m
    cap = cap_m.group(1)
    five_line_patterns = [
        r'5\s*\*\s*var\(--crt-text-line\)',
        r'5em',
        r'5lh',
        r'7em',
        r'72px',
        r'calc\(var\(--crt-text-line\)\s*\*\s*5',
        r'calc\(var\(--crt-text-line\)\s*\*\s*var\(--crt-text-max-lines\)',
        r'5\b.*\*',
    ]
    assert any(re.search(p, cap) for p in five_line_patterns), (
        f'max-height ({cap}) must represent a 5-line cap'
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


# ── Hard-timeout regression: 2026-06-17 ──────────────────────────────
# During manual testing the user reported the post-generation
# redirect was firing prematurely. Root cause: progress.js had a
# 10-minute ``HARD_TIMEOUT_MS`` safety net that, on expiry, called
# ``window.location.href = '/lessons'`` — which 302-bounced to
# /results (lessons not yet saved) and made it LOOK like the
# server-side redirect was firing prematurely. With cloud AI
# (gemma3:27b-cloud) and 3+ modules, generation can take 15-25
# minutes; the 10-minute cap was too aggressive. The new
# contract: when the hard cap expires the JS simply stops polling
# and shows a "still working" message; the user can navigate
# away manually. The cap was extended to 30 minutes.

def test_progress_js_hard_timeout_does_not_redirect():
    """progress.js must NOT redirect to /lessons on hard timeout.

    Previously a 10-minute hard cap fired
    ``window.location.href = '/lessons'`` which 302-bounced to
    /results when lessons were not yet saved, making it appear
    that the redirect was firing prematurely. The new contract:
    on hard-cap expiry the JS stops polling and shows a message.
    """
    js = _read(PROGRESS_JS)

    # The hard-timeout block in the new code must set a bubble
    # message and stop polling — it must NOT navigate to /lessons.
    # Locate the "Hard timeout" comment block and assert no
    # ``window.location.href`` is invoked inside it.
    m = re.search(
        r'//\s*Hard timeout:.*?(?=\n\s*//\s*[A-Z]|\n\s*$)',
        js, re.S,
    )
    assert m, 'progress.js missing the "Hard timeout" comment block'
    block = m.group(0)
    assert 'window.location.href' not in block, (
        'progress.js hard-timeout block must NOT call '
        'window.location.href. The previous behavior of redirecting '
        'to /lessons on hard timeout 302-bounced to /results and '
        'was the root cause of the "premature redirect" user '
        'reports.'
    )
    # The block must call stopProgressPoll and setBubblePersistent
    # so the user knows the page is still working.
    assert 'stopProgressPoll' in block
    assert 'setBubblePersistent' in block


def test_progress_js_hard_timeout_is_at_least_2_hours():
    """HARD_TIMEOUT_MS must be at least 2 hours (7,200,000 ms).

    With cloud AI (gemma3:27b-cloud) and 3+ modules, a full
    generation (lessons + checkpoints + quiz + narration
    script + edge-tts audio) can take 45-90 minutes end-to-end.
    The cap was raised to 2 hours to accommodate the slowest
    realistic cloud-AI run.

    The previous 10-minute cap (600,000 ms) and 30-minute cap
    (1,800,000 ms) were both too aggressive and caused
    false-positive "premature redirect" reports.
    """
    js = _read(PROGRESS_JS)
    m = re.search(
        r'var\s+HARD_TIMEOUT_MS\s*=\s*(\d+)\s*;',
        js,
    )
    assert m, 'progress.js missing HARD_TIMEOUT_MS constant'
    value = int(m.group(1))
    assert value >= 7_200_000, (
        f'HARD_TIMEOUT_MS = {value} ms is less than 2 hours '
        f'(7,200,000 ms). Cloud-AI generation of 3+ modules '
        f'with TTS can take 45-90 minutes end-to-end; the cap '
        f'must accommodate this.'
    )


def test_app_factory_disables_static_file_cache():
    """src/__init__.py must set SEND_FILE_MAX_AGE_DEFAULT=0.

    Flask's dev server sends strong cache headers (12-hour
    max-age) for static files by default. This caused a phantom
    "bug" during manual testing: the new server code was correct
    but the browser kept the OLD ``progress.js`` (with the 10-min
    hard timeout) cached. The fix: disable the dev server's
    static-file cache so the browser revalidates every file on
    every page load.
    """
    src_init = (ROOT / 'src' / '__init__.py').read_text(encoding='utf-8')
    assert "SEND_FILE_MAX_AGE_DEFAULT" in src_init, (
        "src/__init__.py must configure "
        "SEND_FILE_MAX_AGE_DEFAULT to prevent the dev server from "
        "serving stale static files to the browser."
    )
    # Confirm the value is 0 (no-cache). Allow for whitespace
    # between the key and the value.
    m = re.search(
        r"SEND_FILE_MAX_AGE_DEFAULT['\"]?\s*=\s*(\d+)",
        src_init,
    )
    assert m, (
        "SEND_FILE_MAX_AGE_DEFAULT assignment not found in "
        "src/__init__.py"
    )
    value = int(m.group(1))
    assert value == 0, (
        f"SEND_FILE_MAX_AGE_DEFAULT = {value}; expected 0 "
        f"(no-cache) so the browser revalidates static files on "
        f"every page load."
    )


# ── Two-poll design regression: 2026-06-17 ─────────────────────────
# After fixing the 10-minute hard-timeout redirect bug we lost
# real-time bubble updates during the 45-90 minute cloud-AI
# generation (the resolvedPathId gate meant /lessons/generation-status
# wasn't polled until the POST response returned — which is after
# ALL modules are generated). The fix: poll BOTH /progress (for
# cosmetic updates) and /lessons/generation-status (for the redirect
# decision) in parallel. The cosmetic poll must NEVER trigger a
# redirect; the redirect-decision poll must NEVER update the bubble.

def test_progress_js_polls_both_endpoints_in_parallel():
    """progress.js must poll /progress AND /lessons/generation-status.

    /progress is for cosmetic bubble updates (mascot text,
    progress bar fill). It runs as soon as the user clicks
    Generate. /lessons/generation-status is for the redirect
    decision only (generation_completed === true). It runs only
    after the POST response has set resolvedPathId. Together they
    give the user real-time feedback during the 45-90 minute
    cloud-AI generation.
    """
    js = _read(PROGRESS_JS)

    # Cosmetic poll: /progress must be present in startGenerateLessons.
    # Match a fetch to /progress inside the startGenerateLessons
    # function (not inside startProcessProgressPoll).
    start_gen_idx = js.find('window.startGenerateLessons')
    assert start_gen_idx >= 0, 'startGenerateLessons not found'
    start_gen = js[start_gen_idx:]
    assert "'/progress?task_id='" in start_gen or '"/progress?task_id="' in start_gen, (
        'progress.js startGenerateLessons must poll /progress '
        'for cosmetic bubble updates during the long generation.'
    )

    # Redirect-decision poll: /lessons/generation-status must be
    # present in startGenerateLessons.
    assert "'/lessons/generation-status?path_id='" in start_gen or '"/lessons/generation-status?path_id="' in start_gen, (
        'progress.js startGenerateLessons must poll '
        '/lessons/generation-status for the redirect decision.'
    )


def test_progress_js_cosmetic_poll_never_triggers_redirect():
    """The /progress poll must NOT trigger a window.location.href
    redirect.

    The previous code used ``data.stage >= 4`` and ``data.done ===
    true`` from this endpoint to trigger the redirect, which
    caused the premature-redirect bug. The new design uses this
    endpoint only for cosmetic updates and the redirect-decision
    lives exclusively on /lessons/generation-status. This test
    is the regression guard.
    """
    js = _read(PROGRESS_JS)

    start_gen_idx = js.find('window.startGenerateLessons')
    assert start_gen_idx >= 0, 'startGenerateLessons not found'
    start_gen = js[start_gen_idx:]

    # The /progress fetch response handler must NOT contain
    # ``window.location.href`` (which is the redirect action).
    progress_poll_idx = start_gen.find("'/progress?task_id='")
    assert progress_poll_idx >= 0, (
        '/progress cosmetic poll not found in startGenerateLessons'
    )
    # Find the matching ``.then(function (data) { ... })`` block
    # that handles the cosmetic response. Look for the next
    # ``window.location.href`` after the /progress fetch and
    # assert it is NOT inside that .then handler.
    #
    # We approximate "inside the .then handler" by searching for
    # the next ``.catch`` after the /progress fetch — any
    # window.location.href BEFORE the .catch is inside the .then.
    progress_response_idx = start_gen.find(
        '.then(function (data)', progress_poll_idx,
    )
    assert progress_response_idx >= 0, (
        '/progress response handler not found in startGenerateLessons'
    )
    catch_idx = start_gen.find('.catch(function () {}', progress_response_idx)
    assert catch_idx > progress_response_idx, (
        '/progress .catch handler not found after .then handler'
    )

    cosmetic_block = start_gen[progress_response_idx:catch_idx]
    assert 'window.location.href' not in cosmetic_block, (
        '/progress cosmetic poll must NOT trigger '
        'window.location.href. The redirect-decision lives '
        'exclusively on /lessons/generation-status.'
    )
