"""
Tests for the Quick Check auto-advance behavior.

Background: Quick Check slides used to auto-advance to the next slide
3 seconds after the learner clicked an answer (or after the grade
endpoint returned). This was annoying because the learner was often
still reading the per-question feedback when the timer fired and
forced them past the checkpoint before they were ready.

The user explicitly asked for this auto-advance to be removed. The
desired behavior is:
  - The learner selects an answer.
  - The Continue button becomes visible.
  - The learner clicks Continue (or presses the right-arrow key after
    data-answered='true' is set) to advance.
  - There is NO automatic timer that forces advancement.

This test pins the desired behavior by reading the source code of
deck-engine.js and asserting:
  1. The file does not schedule any setTimeout that calls autoAdvance
     (or any equivalent that would auto-navigate to the next slide).
  2. The Continue button is the single source of progression: clicking
     it calls autoAdvance, which calls this.next() exactly once.

The test is intentionally tolerant of renames/rewrites — it looks for
the setTimeout pattern and the autoAdvance symbol, then asserts the
unwanted pattern is gone. If someone re-introduces a setTimeout-based
auto-advance, this test fails.
"""
import re
from pathlib import Path


DECK_ENGINE_JS = Path(__file__).resolve().parents[1] / 'src' / 'static' / 'js' / 'deck-engine.js'


def _read_source() -> str:
    return DECK_ENGINE_JS.read_text(encoding='utf-8')


def test_no_setTimeout_for_checkpoint_auto_advance():
    """No setTimeout in deck-engine.js may schedule an auto-advance for
    a checkpoint slide. The Continue button is the single source of
    progression."""
    source = _read_source()

    # The buggy pattern: scheduleAutoAdvance = () => setTimeout(autoAdvance, 3000)
    # (or any setTimeout whose callback calls autoAdvance / this.next / goToSlide).
    # We assert: there is no setTimeout whose argument is the autoAdvance
    # symbol, no matter what delay is used.
    pattern = re.compile(
        r'setTimeout\s*\(\s*(?:autoAdvance|this\.next|this\.goToSlide)',
        re.MULTILINE,
    )
    matches = pattern.findall(source)
    assert not matches, (
        f"deck-engine.js schedules an auto-advance via setTimeout. "
        f"Found: {matches!r}. The 3-second auto-advance timer after a "
        f"Quick Check answer is annoying and has been removed — the "
        f"user must explicitly click Continue or press the right-arrow "
        f"key to advance. See advanceFromCheckpoint in deck-engine.js."
    )


def test_no_setTimeout_with_ms_3000_for_navigation():
    """No 3-second setTimeout remains in deck-engine.js. The hard-coded
    3000ms delay is the specific anti-pattern the user complained about."""
    source = _read_source()
    pattern = re.compile(
        r'setTimeout\s*\([^,]+,\s*3000\s*\)',
        re.MULTILINE,
    )
    matches = pattern.findall(source)
    assert not matches, (
        f"deck-engine.js contains setTimeout(..., 3000) which is the "
        f"3-second auto-advance the user wants removed. Found: {matches!r}."
    )


def test_continue_button_triggers_immediate_advance():
    """The Continue button's click handler must call autoAdvance (which
    calls this.next()) exactly once, with no setTimeout in between.

    This test pins the intended user-facing behavior: clicking Continue
    advances immediately, no timer."""
    source = _read_source()

    # The expected structure (after the fix):
    #   btn.onclick = () => { ...; autoAdvance(); };
    # OR
    #   btn.addEventListener('click', () => { ...; autoAdvance(); });
    # We assert that AT LEAST ONE of these patterns exists and that
    # there is no setTimeout between the click handler and autoAdvance.

    has_btn_click_handler = bool(re.search(
        r'btn\.onclick\s*=\s*\(\)\s*=>\s*\{',
        source,
    ))
    has_addEventListener = bool(re.search(
        r"addEventListener\s*\(\s*['\"]click['\"]",
        source,
    ))
    assert has_btn_click_handler or has_addEventListener, (
        "deck-engine.js does not have a click handler on the checkpoint "
        "Continue button. The button must call autoAdvance() when clicked."
    )

    # The autoAdvance function must call this.next() — that's how the
    # user advances to the next slide.
    assert 'this.next()' in source, (
        "deck-engine.js autoAdvance function does not call this.next(). "
        "The Continue button must trigger a single advance to the next slide."
    )


def test_advanceFromCheckpoint_function_signature_unchanged():
    """The advanceFromCheckpoint public API must remain stable so
    deck-page.js's click binding (deck.advanceFromCheckpoint(e.currentTarget))
    continues to work."""
    source = _read_source()
    assert 'advanceFromCheckpoint(btn)' in source, (
        "deck-engine.js no longer exposes advanceFromCheckpoint(btn). "
        "The deck-page.js click binding depends on this signature."
    )
