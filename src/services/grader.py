"""
Grading service — evaluates learner answers against question definitions.
Supports mcq, true_false, multi_select, cloze_dropdown, and fill_blank question types.
"""
from typing import Any


def _safe_int(value: Any, default: int = -1) -> int:
    """Convert *value* to int, returning *default* on failure.

    Prevents ValueError 500s when the client sends malformed JSON
    (e.g. a string instead of a number) to the grading endpoint.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def grade_single_question(question: dict, user_answer: Any) -> bool:
    """
    Grade a single question against a user-supplied answer.

    Args:
        question: dict with keys 'type', 'answer_index', 'answer',
                  'answer_indices', 'acceptable_answers', etc.
        user_answer: the learner's response (varies by type).

    Returns:
        True if the answer is correct, False otherwise.
    """
    qtype = question.get("type", "")
    if qtype == "mcq":
        return user_answer is not None and _safe_int(user_answer) == question.get("answer_index", -1)
    elif qtype == "cloze_dropdown":
        return user_answer is not None and _safe_int(user_answer) == question.get("answer_index", -1)
    elif qtype == "true_false":
        if isinstance(user_answer, str):
            user_answer = user_answer.lower() in ("true", "1", "yes")
        return bool(user_answer) == bool(question.get("answer", False))
    elif qtype == "multi_select":
        if not isinstance(user_answer, list):
            user_answer = [_safe_int(user_answer, -2)] if user_answer is not None else []
        correct = question.get("answer_indices", [])
        return set(_safe_int(x, -2) for x in user_answer) == set(correct)
    elif qtype == "fill_blank":
        if "answer_index" in question and "options" in question:
            return user_answer is not None and _safe_int(user_answer) == question.get("answer_index", -1)
        if not isinstance(user_answer, str):
            return False
        ua = user_answer.strip()
        if not ua or " " in ua:
            return False
        acceptable = question.get(
            "acceptable_answers", [question.get("answer", "")]
        )
        return ua.lower() in [a.strip().lower() for a in acceptable if isinstance(a, str)]
    return False


def get_correct_answer(question: dict) -> Any:
    """Return the canonical correct answer for a question dict."""
    qtype = question.get("type", "")
    if qtype == "mcq":
        return question.get("answer_index")
    elif qtype == "cloze_dropdown":
        return question.get("answer_index")
    elif qtype == "true_false":
        return question.get("answer")
    elif qtype == "multi_select":
        return question.get("answer_indices")
    elif qtype == "fill_blank":
        if "answer_index" in question:
            return question.get("answer_index")
        return question.get("answer")
    return None
