"""
Grading service — evaluates learner answers against question definitions.
Supports mcq, true_false, multi_select, cloze_dropdown, fill_blank,
ordering, and matching question types.
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


def _safe_int_list(value: Any) -> list:
    """Normalize a learner answer to a list of ints for sequence grading.

    Non-list input grades as incorrect (never raises). Each element falls
    back to -2 so malformed entries can never accidentally match a valid
    0-based index.
    """
    if not isinstance(value, list):
        return []
    return [_safe_int(x, -2) for x in value]


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
    elif qtype == "ordering":
        # Exact sequence match (all-or-nothing, like multi_select): the
        # learner's order of display indices must equal answer_order.
        # (For proportional scoring see grade_partial_credit below.)
        if not isinstance(user_answer, list):
            return False
        correct = question.get("answer_order", [])
        user = _safe_int_list(user_answer)
        return len(user) == len(correct) == len(question.get("items", [])) and user == list(correct)
    elif qtype == "matching":
        # Exact pairs match (all-or-nothing): per-left chosen rights index
        # must equal answer_indices. (Proportional variant below.)
        if not isinstance(user_answer, list):
            return False
        correct = question.get("answer_indices", [])
        user = _safe_int_list(user_answer)
        return len(user) == len(correct) == len(question.get("lefts", [])) and user == list(correct)
    return False


def grade_partial_credit(question: dict, user_answer: Any) -> float:
    """Score a question proportionally in [0.0, 1.0].

    Ordering scores the fraction of positions placed correctly;
    matching scores the fraction of pairs matched correctly. All other
    types delegate to :func:`grade_single_question` (1.0 or 0.0), so
    checkpoints and quick-recall questions stay all-or-nothing while
    final-quiz sequencing questions reward near-misses. Never raises.
    """
    try:
        qtype = question.get("type", "")
        if qtype == "ordering":
            items = question.get("items", [])
            correct = list(question.get("answer_order", []))
            user = _safe_int_list(user_answer)
            if not items or len(user) != len(correct) or len(correct) != len(items):
                return 0.0
            hits = sum(1 for u, c in zip(user, correct) if u == c)
            return hits / len(correct)
        if qtype == "matching":
            lefts = question.get("lefts", [])
            correct = list(question.get("answer_indices", []))
            user = _safe_int_list(user_answer)
            if not lefts or len(user) != len(correct) or len(correct) != len(lefts):
                return 0.0
            hits = sum(1 for u, c in zip(user, correct) if u == c)
            return hits / len(correct)
        return 1.0 if grade_single_question(question, user_answer) else 0.0
    except Exception:
        return 0.0


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
    elif qtype == "ordering":
        return question.get("answer_order")
    elif qtype == "matching":
        return question.get("answer_indices")
    return None
