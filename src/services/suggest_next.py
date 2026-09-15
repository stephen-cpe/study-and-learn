"""
Suggest-next service — "based on your documents, learn about X next".

Internal (document-grounded) mode only: given the learner's goal, the
planned modules with pass/score state, the document summary, and the
relevance verdict, an LLM proposes up to 3 follow-up topics that are
covered by the uploaded materials but NOT yet taught (or not yet passed).
No web search — external suggestions are a deferred phase.

Never raises: any AI/parse failure yields ``{"suggestions": []}`` so the
lessons page renders normally without a suggestion card.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.services.ai_client import call_ollama
from src.services.llm_json import extract_json

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 3


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…"


def build_suggestion_prompt(
    learning_goal: str,
    modules: List[Dict[str, Any]],
    summary: str = "",
    missing_material: str = "",
) -> str:
    """Assemble the suggest-next prompt (pure string assembly, unit-testable)."""
    lines = []
    for m in modules or []:
        state = "passed" if m.get("passed") else ("completed" if m.get("completed") else "not passed")
        score = m.get("score")
        lines.append(f"- {m.get('title', 'Untitled')} [{state}"
                     + (f", score {score}%" if score is not None else "") + "]")
    module_list = "\n".join(lines) if lines else "(no modules)"
    return f"""You are an expert tutor helping a learner decide what to study next.
Learning Goal: {learning_goal}

Planned modules and their state:
{module_list}

Document Summary:
{_truncate(summary, 2000)}

Known gaps from the initial relevance check:
{_truncate(missing_material, 1000) or "(none recorded)"}

TASK: Propose up to {MAX_SUGGESTIONS} follow-up topics that are covered by the
uploaded documents but NOT yet taught (not in the module list above) or NOT
yet passed. Each suggestion needs a one-sentence reason grounded in the
documents and a short source reference (e.g. a document section or filename).
If every topic appears taught and passed, return an empty suggestions array.

Respond with ONLY a JSON object — no prose, no markdown.
JSON FORMAT:
{{
  "suggestions": [
    {{"title": "...", "reason": "...", "source_refs": "..."}}
  ]
}}
"""


def compute_suggestions(
    learning_goal: str,
    modules: List[Dict[str, Any]],
    summary: str = "",
    missing_material: str = "",
) -> Dict[str, Any]:
    """Compute follow-up topic suggestions (never raises)."""
    try:
        prompt = build_suggestion_prompt(learning_goal, modules, summary, missing_material)
        response = call_ollama(prompt)
        result = extract_json(response)
        raw = (result or {}).get("suggestions", []) if isinstance(result, dict) else []
        suggestions = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title or title.lower() in seen:
                continue
            # Never suggest something already planned — the module list is
            # the source of truth for "taught".
            planned = {(m.get("title", "") or "").strip().lower() for m in (modules or [])}
            if title.lower() in planned:
                continue
            seen.add(title.lower())
            suggestions.append({
                "title": title[:200],
                "reason": str(item.get("reason", "")).strip()[:1000],
                "source_refs": str(item.get("source_refs", "")).strip()[:500],
            })
            if len(suggestions) >= MAX_SUGGESTIONS:
                break
        return {"suggestions": suggestions}
    except Exception as e:
        logger.warning("compute_suggestions failed: %s", str(e))
        return {"suggestions": []}
