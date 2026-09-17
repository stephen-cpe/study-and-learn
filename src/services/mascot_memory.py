"""
Mascot memory store — long-term per-learner memory for the personality engine.

Three memory types (mirrors the Eternal Fusion Pavilion pattern):
* ``semantic``    — stable preferences ("prefers Hard difficulty")
* ``episodic``    — events ("finished module 3 of Cell Biology")
* ``procedural``  — how-to ("likes to be called Bobby")

The mascot's line generator calls :func:`get_memories` at speak time and
injects them into the LLM context as a ``[Learner Profile]`` block.

Write triggers (module completed, quiz passed, lesson generated, settings
changed) call :func:`store_memory` — a cheap single INSERT that never
blocks the response.  All functions are no-ops on unknown errors (the
mascot must never crash a learning session).
"""
from __future__ import annotations

import logging

from src import db
from src.models import MascotMemory

logger = logging.getLogger(__name__)

VALID_TYPES = MascotMemory.VALID_TYPES

# Hygiene caps: memories are append-only, so without pruning the table
# grows forever while reads only ever take the newest handful. Coalescing
# also keeps repeats like "Prefers Hard difficulty" ×5 from stacking up.
MAX_MEMORIES_PER_USER = 200
COALESCE_WINDOW = 20


def store_memory(user_id: str, memory_type: str, content: str) -> MascotMemory | None:
    """Store one memory for a learner.

    A no-op (returns ``None``) when the type is invalid or the content
    is empty — never raises.  Callers do not need try/except.
    """
    if memory_type not in VALID_TYPES:
        logger.warning("store_memory: invalid type %r", memory_type)
        return None
    content = (content or '').strip()
    if not content:
        return None
    try:
        # Coalesce: an identical memory among the most recent rows adds
        # no information — return the existing row instead of stacking.
        recent = (db.session.query(MascotMemory)
                  .filter_by(user_id=user_id)
                  .order_by(MascotMemory.created_at.desc())
                  .limit(COALESCE_WINDOW).all())
        for row in recent:
            if row.memory_type == memory_type and (row.content or '').strip() == content:
                return row
        mem = MascotMemory(user_id=user_id, memory_type=memory_type,
                           content=content)
        db.session.add(mem)
        db.session.commit()
        logger.info("store_memory: %s → [%s] %s", user_id[:8],
                    memory_type, content[:80])
        # Prune: keep only the newest MAX_MEMORIES_PER_USER rows so the
        # table stays bounded while reads (newest-first) never notice.
        try:
            stale_ids = [r.id for r in (db.session.query(MascotMemory.id)
                         .filter_by(user_id=user_id)
                         .order_by(MascotMemory.created_at.desc())
                         .offset(MAX_MEMORIES_PER_USER).all())]
            if stale_ids:
                (db.session.query(MascotMemory)
                 .filter(MascotMemory.id.in_(stale_ids))
                 .delete(synchronize_session=False))
                db.session.commit()
        except Exception:
            db.session.rollback()
        return mem
    except Exception:
        db.session.rollback()
        logger.warning("store_memory: failed for %s", user_id[:8],
                       exc_info=True)
        return None


def get_memories(user_id: str, limit: int = 20) -> list[dict]:
    """Return the learner's memories, newest first.

    Each dict has ``memory_type``, ``content``, and ``created_at`` keys.
    Returns ``[]`` on any error — the mascot degrades to a nameless line.
    """
    try:
        rows = (db.session.query(MascotMemory)
                .filter_by(user_id=user_id)
                .order_by(MascotMemory.created_at.desc())
                .limit(limit)
                .all())
        return [{'memory_type': r.memory_type, 'content': r.content,
                 'created_at': r.created_at}
                for r in rows]
    except Exception:
        logger.warning("get_memories: failed for %s", user_id[:8],
                       exc_info=True)
        return []


def delete_all(user_id: str) -> int:
    """Delete all memories for a learner (forget-me).  Returns count."""
    try:
        count = (db.session.query(MascotMemory)
                 .filter_by(user_id=user_id).delete())
        db.session.commit()
        logger.info("delete_all: %s → %d memories", user_id[:8], count)
        return count
    except Exception:
        db.session.rollback()
        logger.warning("delete_all: failed for %s", user_id[:8],
                       exc_info=True)
        return 0