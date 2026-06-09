"""
Shared helpers for routes — session-to-DB fallback resolution.

Extracts the repeated pattern of "prefer session, fall back to DB"
used by multiple route handlers.
"""
import json
from typing import Any, List

from flask import session

from flask_login import current_user

from src.repositories.lesson_repo import (
    get_extracted_texts as _db_get_texts,
    get_file_names as _db_get_filenames,
    get_learning_goal as _db_get_goal,
    get_most_recent_active_path,
)


def _resolve_goal() -> str:
    """Return the current learning goal, preferring session, falling back to DB."""
    from_session = session.get('learning_goal', '')
    if from_session:
        return from_session
    path = get_most_recent_active_path(current_user)
    return path.learning_goal if path else ''


def _resolve_texts() -> List[str]:
    """Return extracted texts, preferring session, falling back to DB."""
    texts = session.get('extracted_texts', [])
    if texts:
        return texts
    return _db_get_texts(current_user) or []


def _resolve_hashes() -> List[str]:
    """Return file hashes, preferring session, falling back to DB."""
    hashes = session.get('file_hashes', [])
    if hashes:
        return hashes
    path = get_most_recent_active_path(current_user)
    if path and path.file_hashes:
        try:
            return json.loads(path.file_hashes)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _resolve_filenames() -> List[str]:
    """Return original filenames, preferring session, falling back to DB."""
    fnames = session.get('uploaded_filenames', [])
    if fnames:
        return fnames
    return _db_get_filenames(current_user) or []


def _build_retriever(
    goal: str,
    texts: List[str],
    hashes: List[str],
    file_names: List[str] = None,
) -> Any:
    """Build the correct retriever (hashed or flat-text) for the current state.

    When both ``hashes`` and ``file_names`` are available, uses a
    sources-aware retriever that includes resolved filenames in the
    source citation metadata.

    Args:
        goal: The learning goal for context queries.
        texts: Extracted flat text content.
        hashes: SHA-256 file hashes for content-keyed ChromaDB lookups.
        file_names: Original filenames (one per hash) for display.

    Returns:
        A callable retriever that accepts a query string and returns a
        dict with ``context_text`` and ``sources``.
    """
    from src.services.lesson_orchestrator import (
        make_retriever,
        make_retriever_from_hashes,
        make_retriever_from_hashes_with_names,
    )
    if hashes and file_names:
        return make_retriever_from_hashes_with_names(goal, hashes, file_names)
    if hashes:
        return make_retriever_from_hashes(goal, hashes)
    return make_retriever(goal, texts)
