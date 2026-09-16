"""
TTS persona — tutor-voice styles and memory filtering for narration.

The mascot's ``mascot_persona.py`` targets a 70-char CRT bubble. TTS
narration is spoken aloud (40-60 words per slot, plain text, no SSML),
so it needs its own voice styles and a filtered learner context.

Speakers are edge-tts voices (see ``tts_service.SPEAKER_VOICES``), not
agents — there is no per-speaker memory table. All memory lives in the
single ``MascotMemory`` table; this module only selects which memories
are relevant to spoken narration.
"""
from __future__ import annotations

SPEAKER_STYLE = {
    'Ava': 'warm, encouraging female tutor, steady pace',
    'Emma': 'bright, upbeat female tutor, slightly faster pace',
    'Ryan': 'calm British male tutor, measured and clear',
    'Andrew': 'friendly American male tutor, conversational',
}

DEFAULT_SPEAKER = 'Ava'

# Voice-preference echoes ("Prefers TTS voice Ava") add no value to
# narration — the player already uses that voice. Drop them.
_VOICE_PREF_MARKERS = ('prefers tts voice', 'tts speaker', 'tts voice')


def _as_text(item) -> tuple[str, str]:
    """Normalize a memory item to (memory_type, content).

    Accepts MascotMemory dicts (``{'memory_type':..., 'content':...}``)
    and plain strings (treated as episodic). Returns ('', '') for junk.
    """
    if isinstance(item, dict):
        content = str(item.get('content', '') or '').strip()
        mtype = str(item.get('memory_type', '') or '').strip().lower()
        if not content:
            return '', ''
        return mtype or 'episodic', content
    if isinstance(item, str):
        content = item.strip()
        if not content:
            return '', ''
        return 'episodic', content
    return '', ''


def _is_voice_pref_echo(content: str) -> bool:
    lowered = content.lower()
    return any(m in lowered for m in _VOICE_PREF_MARKERS)


def filter_memories_for_tts(memories: list | None, limit: int = 5) -> list[str]:
    """Select narration-relevant memory strings, most useful first.

    Priority: struggle/mastery signals > recent episodic > semantic >
    procedural. Voice-preference echoes are dropped. Never raises —
    returns [] on any unexpected input.
    """
    try:
        if not memories:
            return []
        scored: list[tuple[int, str]] = []
        for item in memories:
            mtype, content = _as_text(item)
            if not content:
                continue
            if _is_voice_pref_echo(content):
                continue
            text = content[:120]
            lowered = text.lower()
            # Struggle / mastery signals are most speakable.
            if 'struggl' in lowered or 'failed' in lowered or 'did not pass' in lowered:
                score = 0
            elif 'mastered' in lowered or 'passed' in lowered or '90%' in lowered or '100%' in lowered:
                score = 1
            elif mtype == 'episodic':
                score = 2
            elif mtype == 'semantic':
                score = 3
            else:
                score = 4
            scored.append((score, text))
        scored.sort(key=lambda t: t[0])
        seen: set[str] = set()
        out: list[str] = []
        for _, text in scored:
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def build_tts_context_block(
    speaker: str = DEFAULT_SPEAKER,
    display_name: str = '',
    difficulty: str = 'Normal',
    filtered_memories: list[str] | None = None,
) -> str:
    """Build the short TTS context block for the narration prompt."""
    style = SPEAKER_STYLE.get(speaker, SPEAKER_STYLE[DEFAULT_SPEAKER])
    lines = [f"Voice: {speaker} ({style}).", f"Learner: {display_name or 'learner'} ({difficulty})."]
    mems = [m for m in (filtered_memories or []) if isinstance(m, str) and m.strip()][:5]
    if mems:
        lines.append(
            "Things we know about this learner:\n"
            + "\n".join(f"- {m.strip()}" for m in mems)
            + "\nYou may reference at most ONE of these facts naturally in the "
              "intro (-1) where genuinely relevant. Never force it; never list facts."
        )
    return "\n".join(lines)
