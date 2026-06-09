"""
Lesson orchestration service — generates lesson slides, inline checkpoints,
and final quizzes for a single module.  Extracted from routes.py to keep
route handlers thin and testable.
"""
from typing import Callable, Dict, Any, List

from src.services.rag_retriever import build_rag_context, build_rag_context_from_hashes, build_rag_context_from_hashes_with_sources
from src.services.lesson_generator import generate_lesson
from src.services.quiz_generator import generate_quiz, generate_inline_checkpoint


def make_retriever(goal: str, extracted_texts: List[str]) -> Callable[[str], Dict[str, Any]]:
    """Build a simple retriever that returns RAG context for a query.

    Returns:
        A callable that accepts a query string and returns a dict with
        ``context_text`` (str) and ``sources`` (empty list — flat text
        mode has no ChromaDB source provenance).
    """
    def retrieve(query: str) -> Dict[str, Any]:
        text = build_rag_context(goal, extracted_texts) if extracted_texts else ""
        return {"context_text": text, "sources": []}
    return retrieve


def make_retriever_from_hashes(goal: str, file_hashes: List[str]) -> Callable[[str], Dict[str, Any]]:
    """Build a retriever that queries content-keyed ChromaDB collections.

    Returns:
        A callable that accepts a query string and returns a dict with
        ``context_text`` (str) and ``sources`` (list of source dicts with
        chunk_id, source_hash, score, text).
    """
    def retrieve(query: str) -> Dict[str, Any]:
        try:
            result = build_rag_context_from_hashes_with_sources(goal, file_hashes)
            return result
        except Exception:
            return {"context_text": "", "sources": []}
    return retrieve


def make_retriever_from_hashes_with_names(
    goal: str, file_hashes: List[str], file_names: List[str]
) -> Callable[[str], Dict[str, Any]]:
    """Build a retriever that returns sources with resolved filenames.

    Unlike ``make_retriever_from_hashes``, this variant also receives
    the original filenames so that source entries include human-readable
    filenames (rendering "my_notes.pdf" instead of a hash prefix).

    Args:
        goal: The learning goal for context queries.
        file_hashes: SHA-256 file hashes.
        file_names: Original filenames, one per hash.

    Returns:
        Callable that returns dict with ``context_text`` and ``sources``.
    """
    def retrieve(query: str) -> Dict[str, Any]:
        try:
            result = build_rag_context_from_hashes_with_sources(goal, file_hashes, file_names)
            return result
        except Exception:
            return {"context_text": "", "sources": []}
    return retrieve


def build_module_artifacts(
    module: Dict[str, Any],
    learning_goal: str,
    retriever: Callable[[str], Dict[str, Any]],
    existing_slides: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate (or reuse) lesson slides, inline checkpoints, and a final quiz
    for a single module.

    Args:
        module: dict containing at least 'title'.
        learning_goal: the learner's stated goal.
        retriever: callable that accepts a query string and returns a dict
            with ``context_text`` and ``sources``.
        existing_slides: when provided, lesson generation is skipped and these
            slides are used directly (e.g. during a retake).

    Returns:
        dict with keys: 'lesson', 'quiz', 'checkpoints', 'sources'.
    """
    module_title = module.get("title", "")

    if existing_slides is not None:
        lesson_data = {"slides": existing_slides, "sources": []}
    else:
        lesson_data = generate_lesson(module_title, learning_goal, retriever)

    slides = lesson_data.get("slides", [])
    sources = lesson_data.get("sources", [])
    quiz_data = generate_quiz(module_title, slides, retriever, n_questions=5)
    checkpoints = _build_checkpoints(slides, module_title, retriever)

    return {
        "lesson": lesson_data,
        "quiz": quiz_data,
        "checkpoints": checkpoints,
        "sources": sources,
    }


def _build_checkpoints(
    slides: List[Dict[str, Any]],
    module_title: str,
    retriever: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    """Insert inline comprehension checkpoints at ~1/3 intervals."""
    checkpoints: Dict[str, Any] = {}
    if len(slides) > 2:
        interval = max(1, len(slides) // 3)
        for idx in range(interval - 1, len(slides) - 1, interval):
            slides_subset = slides[max(0, idx - 1) : idx + 1]
            cp = generate_inline_checkpoint(module_title, slides_subset, retriever)
            checkpoints[str(idx)] = cp
        if len(slides) > 1:
            last_checkpoint_slide = max(0, len(slides) - 2)
            if str(last_checkpoint_slide) not in checkpoints:
                slides_subset = slides[
                    max(0, last_checkpoint_slide - 1) : last_checkpoint_slide + 1
                ]
                cp = generate_inline_checkpoint(module_title, slides_subset, retriever)
                checkpoints[str(last_checkpoint_slide)] = cp
    return checkpoints
