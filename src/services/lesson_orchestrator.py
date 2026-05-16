"""
Lesson orchestration service — generates lesson slides, inline checkpoints,
and final quizzes for a single module.  Extracted from routes.py to keep
route handlers thin and testable.
"""
from typing import Callable, Dict, Any, List

from src.services.rag_retriever import build_rag_context
from src.services.lesson_generator import generate_lesson
from src.services.quiz_generator import generate_quiz, generate_inline_checkpoint


def make_retriever(goal: str, extracted_texts: List[str]) -> Callable[[str], str]:
    """Build a simple retriever that returns RAG context for a query."""
    def retrieve(query: str) -> str:
        return build_rag_context(goal, extracted_texts) if extracted_texts else ""
    return retrieve


def build_module_artifacts(
    module: Dict[str, Any],
    learning_goal: str,
    retriever: Callable[[str], str],
    existing_slides: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate (or reuse) lesson slides, inline checkpoints, and a final quiz
    for a single module.

    Args:
        module: dict containing at least 'title'.
        learning_goal: the learner's stated goal.
        retriever: callable that accepts a query string and returns RAG context.
        existing_slides: when provided, lesson generation is skipped and these
            slides are used directly (e.g. during a retake).

    Returns:
        dict with keys: 'lesson', 'quiz', 'checkpoints'.
    """
    module_title = module.get("title", "")

    if existing_slides is not None:
        lesson_data = {"slides": existing_slides}
    else:
        lesson_data = generate_lesson(module_title, learning_goal, retriever)

    slides = lesson_data.get("slides", [])
    quiz_data = generate_quiz(module_title, slides, retriever, n_questions=5)
    checkpoints = _build_checkpoints(slides, module_title, retriever)

    return {
        "lesson": lesson_data,
        "quiz": quiz_data,
        "checkpoints": checkpoints,
    }


def _build_checkpoints(
    slides: List[Dict[str, Any]],
    module_title: str,
    retriever: Callable[[str], str],
) -> Dict[str, Any]:
    """Insert inline comprehension checkpoints at ~⅓ intervals."""
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
