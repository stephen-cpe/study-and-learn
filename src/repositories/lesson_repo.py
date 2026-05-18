"""
DB-backed lesson repository — persists lessons to StudyPath.content_data
and module progress to LessonProgress rows.

Replaces the session-backed session_repo.py (Sprint 5 Phase 2.2).
"""
import json
from typing import Any, Dict, List

from src import db
from src.models import StudyPath, LessonProgress
from flask_login import current_user


def get_lessons(user=None) -> List[Dict[str, Any]]:
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return []

    path = StudyPath.query.filter_by(user_id=user.id, status='active').first()
    if not path or not path.content_data:
        return []

    try:
        lessons = json.loads(path.content_data)
    except (json.JSONDecodeError, TypeError):
        return []

    progress_rows = {
        lp.module_index: lp
        for lp in LessonProgress.query.filter_by(study_path_id=path.id).all()
    }

    for lesson in lessons:
        idx = lesson.get('index')
        lp = progress_rows.get(idx)
        if lp:
            lesson['score'] = lp.score
            lesson['passed'] = lp.passed
            lesson['completed'] = lp.completed

    return lessons


def save_lessons(lessons: List[Dict[str, Any]], user=None,
                 title: str = None, learning_goal: str = None) -> None:
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return

    path = StudyPath.query.filter_by(user_id=user.id, status='active').first()
    if not path:
        path = StudyPath(
            user_id=user.id,
            title=title or 'Study Path',
            learning_goal=learning_goal or '',
            status='active',
        )
        db.session.add(path)
    elif title or learning_goal:
        if title:
            path.title = title
        if learning_goal:
            path.learning_goal = learning_goal

    path.content_data = json.dumps(lessons)
    path.updated_at = db.func.now()

    existing_rows = {
        lp.module_index: lp
        for lp in LessonProgress.query.filter_by(study_path_id=path.id).all()
    }

    for lesson in lessons:
        idx = lesson.get('index')
        if idx is None:
            continue
        lp = existing_rows.pop(idx, None)
        if lp is None:
            lp = LessonProgress(
                study_path_id=path.id,
                module_index=idx,
            )
            db.session.add(lp)
        lp.score = lesson.get('score')
        lp.passed = lesson.get('passed', False)
        lp.completed = lesson.get('completed', False)

    for stale_lp in existing_rows.values():
        db.session.delete(stale_lp)

    db.session.commit()
