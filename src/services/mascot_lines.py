"""
Mascot line generator — calls the LLM (via the existing ``ai_client``)
to produce a short, personalized, in-character line for the speech bubble.

Falls back to a static array on any error (LLM down, timeout, AI_MOCK
mode) so the robot always has something to say.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.services.ai_client import call_ollama
from src.services.mascot_memory import get_memories
from src.services.mascot_persona import SYSTEM_PROMPT, build_context_block

logger = logging.getLogger(__name__)

MAX_LINE_LENGTH = 70

# Static fallback lines per event — used when the LLM is unavailable.
# These are generic enough to work without context.
FALLBACK_LINES = {
    'idle': [
        'Ready to learn?',
        'Take a break!',
        'I see you studying...',
        'You got this!',
        'Knowledge = power!',
    ],
    'dashboard': [
        'Welcome back! Pick up where you left off.',
        'Your dashboard looks good!',
        'Ready for another round?',
    ],
    'lessons': [
        'Nice work getting this far!',
        'Keep going — you are almost there.',
        'Every module counts!',
    ],
    'lesson_complete': [
        'Lesson complete! Big brain move.',
        'You crushed that module!',
        'Another one down. Nice!',
    ],
    'error': [
        'Something went wrong. Try again?',
        'Oops — glitch in the matrix.',
        'Minor hiccup. Retry when ready.',
    ],
    'progress': [
        'Working on it...',
        'Crunching the numbers...',
        'Almost there!',
    ],
}

# In-memory cache: (user_id, event) → (line, timestamp)
# Prevents an LLM call on every 15s idle tick when context hasn't changed.
_line_cache: dict[tuple[str, str], tuple[str, float]] = {}
_CACHE_TTL_S = 30.0


def _is_cached(user_id: str, event: str) -> str | None:
    """Return a cached line if fresh (< 30s), else None."""
    key = (user_id, event)
    entry = _line_cache.get(key)
    if entry is None:
        return None
    line, ts = entry
    age = (datetime.now(timezone.utc).timestamp()) - ts
    if age < _CACHE_TTL_S:
        return line
    _line_cache.pop(key, None)
    return None


def _set_cache(user_id: str, event: str, line: str) -> None:
    _line_cache[(user_id, event)] = (line,
                                      datetime.now(timezone.utc).timestamp())


def _fallback(event: str) -> str:
    """Pick a random-ish fallback line for the event."""
    lines = FALLBACK_LINES.get(event, FALLBACK_LINES['idle'])
    # Avoid repeating the same line on consecutive calls: pick based on
    # a simple time-based rotation.
    idx = int(datetime.now(timezone.utc).timestamp()) % len(lines)
    return lines[idx]


def generate_line(user_id: str,
                  display_name: str,
                  event: str = 'idle',
                  path_title: str | None = None,
                  progress_pct: int | None = None,
                  page: str | None = None) -> str:
    """Generate one short, personalized mascot line.

    Args:
        user_id: The learner's user ID (for memory retrieval + caching).
        display_name: The learner's friendly name (nickname/full_name/username).
        event: What triggered the speak — 'idle', 'dashboard', 'lessons',
            'lesson_complete', 'error', 'progress'.
        path_title: The title of the learner's current active study path.
        progress_pct: Progress percentage on the current path.
        page: The page the learner is on (e.g. 'dashboard', 'lessons').

    Returns:
        A string ≤ 120 chars, never empty, never raises.
    """
    # Check cache first — avoids an LLM call on every 15s idle tick
    cached = _is_cached(user_id, event)
    if cached:
        return cached

    # Retrieve memories
    memories = get_memories(user_id, limit=10)

    # Build the LLM prompt
    context = build_context_block(
        memories, display_name,
        path_title=path_title,
        progress_pct=progress_pct,
        event=event,
        page=page,
    )
    prompt = f"{SYSTEM_PROMPT}\n\n{context}\n\nGenerate ONE line:"

    # Call the LLM
    try:
        raw = call_ollama(prompt)
        line = (raw or '').strip().strip('"').strip("'").strip()
        # Enforce the character limit
        if len(line) > MAX_LINE_LENGTH:
            line = line[:MAX_LINE_LENGTH - 3] + '...'
        if not line:
            line = _fallback(event)
        _set_cache(user_id, event, line)
        logger.info("generate_line: %s/%s → %r", user_id[:8], event,
                    line[:80])
        return line
    except Exception:
        logger.warning("generate_line: LLM call failed, using fallback",
                       exc_info=True)
        line = _fallback(event)
        _set_cache(user_id, event, line)
        return line