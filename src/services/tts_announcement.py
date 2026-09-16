"""
TTS announcements — short on-demand spoken lines outside the slide deck.

Two kinds (Stage 2):
* ``lesson_complete`` — spoken results + optional top suggestion:
  "Nice work, {name}! You passed {title} with {score}%. Based on your
  uploads, I recommend {suggestion} — {reason}"
* ``suggestion`` — spoken Keep-Learning card:
  "Based on your uploaded documents, I suggest {title}. {reason}"

Plain text only (edge-tts has no SSML). Never raises — falls back to a
short generic line so the deck never blocks on announcements.
"""
from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger(__name__)

MAX_ANNOUNCE_CHARS = 400

# Simple per-user rate limit: 10 generations per 60s window. In-memory
# only (single-worker gunicorn) — exceeding returns 429, never blocks.
_RATE: dict[str, tuple[int, float]] = {}
_RATE_LIMIT = 10
_RATE_WINDOW_S = 60.0


def _clean(text: str) -> str:
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    # Strip markdown that would sound wrong aloud.
    text = text.replace('**', '').replace('__', '').replace('`', '')
    return text


def check_rate_limit(user_id: str) -> bool:
    """Return True if allowed, False if rate-limited. Never raises."""
    try:
        now = time.time()
        count, start = _RATE.get(user_id, (0, now))
        if now - start >= _RATE_WINDOW_S:
            _RATE[user_id] = (1, now)
            return True
        if count >= _RATE_LIMIT:
            return False
        _RATE[user_id] = (count + 1, start)
        return True
    except Exception:
        return True


def build_announcement_text(
    kind: str = 'lesson_complete',
    display_name: str = 'learner',
    module_title: str | None = None,
    score: int | None = None,
    passed: bool | None = None,
    suggestion: dict | None = None,
    is_external: bool = False,
) -> str:
    """Build short spoken announcement text (<=400 chars, never empty)."""
    try:
        name = _clean(display_name) or 'learner'
        title = _clean(module_title) if module_title else ''
        sug_title = _clean((suggestion or {}).get('title', '')) if suggestion else ''
        sug_reason = _clean((suggestion or {}).get('reason', '')) if suggestion else ''
        if sug_reason and len(sug_reason) > 160:
            sug_reason = sug_reason[:157] + '...'
        web_prefix = ' From the web.' if is_external else ''

        if kind == 'suggestion':
            if sug_title:
                base = 'Based on your uploaded documents' if not is_external else 'You finished your documents'
                text = f"{base}, I suggest {sug_title}.{web_prefix}"
                if sug_reason:
                    text += f" {sug_reason}"
                text += " Say generate to create materials for it."
            else:
                text = f"{name}, keep going — complete more modules to unlock suggestions."
        else:  # lesson_complete
            if title and score is not None:
                verb = 'passed' if passed else 'finished'
                text = f"Nice work, {name}! You {verb} {title} with {score}%."
            elif title:
                text = f"Nice work, {name}! You finished {title}."
            else:
                text = f"Nice work, {name}! Lesson complete."
            if sug_title:
                text += f" Based on your uploads, I recommend {sug_title}.{web_prefix}"
                if sug_reason:
                    text += f" {sug_reason}"
            else:
                text += " Head back to modules when ready."

        text = _clean(text)
        if len(text) > MAX_ANNOUNCE_CHARS:
            text = text[:MAX_ANNOUNCE_CHARS - 3] + '...'
        return text or f"Nice work, {name}!"
    except Exception:
        logger.warning("build_announcement_text failed", exc_info=True)
        return "Nice work! Head back to modules when ready."
