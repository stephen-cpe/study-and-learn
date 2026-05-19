"""
DB-backed lesson repository — persists lessons to StudyPath.content_data
and module progress to LessonProgress rows.

Replaces the session-backed session_repo.py (Sprint 5 Phase 2.2).
"""
import json
from typing import Any, Dict, List, Optional

from src import db
from src.models import StudyPath, LessonProgress
from flask_login import current_user


def get_lessons(user=None, path_id: str = None) -> List[Dict[str, Any]]:
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return []

    query = StudyPath.query.filter_by(user_id=user.id, status='active')
    if path_id:
        query = query.filter(StudyPath.id == path_id)
    path = query.first()
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


def get_active_path(user=None) -> Optional[StudyPath]:
    """Return the user's active StudyPath or None."""
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return None
    return StudyPath.query.filter_by(user_id=user.id, status='active').first()


def get_extracted_texts(user=None, path_id: str = None) -> List[str]:
    """Return persisted extracted texts from the user's active StudyPath."""
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return []
    query = StudyPath.query.filter_by(user_id=user.id, status='active')
    if path_id:
        query = query.filter(StudyPath.id == path_id)
    path = query.first()
    if not path or not path.extracted_texts:
        return []
    try:
        return json.loads(path.extracted_texts)
    except (json.JSONDecodeError, TypeError):
        return []


def get_learning_goal(user=None, path_id: str = None) -> Optional[str]:
    """Return the learning goal from the user's active StudyPath."""
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return None
    query = StudyPath.query.filter_by(user_id=user.id, status='active')
    if path_id:
        query = query.filter(StudyPath.id == path_id)
    path = query.first()
    if not path:
        return None
    return path.learning_goal


def get_study_path_data(user=None) -> Optional[Dict[str, Any]]:
    """Return the study_path dict (with modules) from the user's active StudyPath content_data."""
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return None
    path = StudyPath.query.filter_by(user_id=user.id, status='active').first()
    if not path or not path.content_data:
        return None
    try:
        data = json.loads(path.content_data)
        if 'modules' in data:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def save_lessons(lessons: List[Dict[str, Any]], user=None,
                 title: str = None, learning_goal: str = None,
                 extracted_texts: List[str] = None) -> None:
    if user is None:
        user = current_user
    if not user or not user.is_authenticated:
        return

    if not title:
        existing = get_active_path(user)
        if existing:
            title = existing.title
        else:
            title = 'Study Path'
    if not learning_goal:
        existing = get_active_path(user)
        if existing:
            learning_goal = existing.learning_goal
        else:
            learning_goal = ''

    path = StudyPath.query.filter_by(user_id=user.id, status='active').first()
    if not path:
        path = StudyPath(
            user_id=user.id,
            title=title,
            learning_goal=learning_goal,
            status='active',
        )
        db.session.add(path)
    else:
        path.title = title
        path.learning_goal = learning_goal

    path.content_data = json.dumps(lessons)
    if extracted_texts is not None:
        path.extracted_texts = json.dumps(extracted_texts)
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
