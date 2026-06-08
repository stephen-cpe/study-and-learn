"""
Repository seam for lesson persistence.

Currently backed by Flask server-side session (cachelib FileSystemCache).
Swap the implementation below in Sprint 5 Phase 2 when moving to a
persistent database store (e.g. PostgreSQL-backed LessonRepository).
"""
from typing import Any, Dict, List

import flask


def get_lessons() -> List[Dict[str, Any]]:
    """Repository seam for lesson persistence — swap implementation in Sprint 5 Phase 2"""
    return flask.session.get("lessons", [])


def save_lessons(lessons: List[Dict[str, Any]]) -> None:
    """Repository seam for lesson persistence — swap implementation in Sprint 5 Phase 2"""
    flask.session["lessons"] = lessons
    flask.session.modified = True
