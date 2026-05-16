"""
Grading service — evaluates learner answers against question definitions.
Supports mcq, true_false, multi_select, and fill_blank question types.
"""
from typing import Any


def normalize_answer(value: Any) -> str:
    """Return a lower-cased, whitespace-trimmed string for comparison."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    return str(value).strip().lower()


def _grade_single_question(question: dict, user_answer: Any) -> bool:
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
        return user_answer is not None and int(user_answer) == question.get("answer_index", -1)
    elif qtype == "true_false":
        if isinstance(user_answer, str):
            user_answer = user_answer.lower() in ("true", "1", "yes")
        return bool(user_answer) == bool(question.get("answer", False))
    elif qtype == "multi_select":
        if not isinstance(user_answer, list):
            user_answer = [int(user_answer)] if user_answer is not None else []
        correct = question.get("answer_indices", [])
        return set(int(x) for x in user_answer) == set(correct)
    elif qtype == "fill_blank":
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


def _get_correct_answer(question: dict) -> Any:
    """Return the canonical correct answer for a question dict."""
    qtype = question.get("type", "")
    if qtype == "mcq":
        return question.get("answer_index")
    elif qtype == "true_false":
        return question.get("answer")
    elif qtype == "multi_select":
        return question.get("answer_indices")
    elif qtype == "fill_blank":
        return question.get("answer")
    return None
