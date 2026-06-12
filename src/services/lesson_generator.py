"""
Lesson generation service for the Study-and-Learn MVP.

Generates RAG-grounded interactive slide-based lessons with four slide types:
title, content, example, and summary. Falls back to a generic placeholder
lesson when AI generation fails or returns unparseable output.
"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError

logger = logging.getLogger(__name__)


HUMOR_NOTE = (
    "TONE NOTE: For example slides only, a light-hearted analogy or a mildly "
    "absurd-but-fitting comparison is encouraged if it genuinely helps illustrate "
    "the concept. Never undermine the educational content. One well-placed wit per "
    "lesson is enough.\n"
)


def build_rag_context_for_module(
    module_title: str,
    learning_goal: str,
    retriever: Optional[Callable[[str], Dict[str, Any]]],
) -> Dict[str, Any]:
    """Query the retriever for context relevant to a module.

    Args:
        module_title: The module title to build a query around.
        learning_goal: The learner's stated goal.
        retriever: A callable that accepts a query string and returns a dict
            with ``context_text`` (str) and ``sources`` (list), or None.

    Returns:
        Dict with ``context_text`` (str) and ``sources`` (list).
    """
    try:
        if retriever:
            query = f"{learning_goal} {module_title}"
            return retriever(query) or {"context_text": "", "sources": []}
    except Exception as e:
        logger.warning("RAG retrieval failed for module '%s': %s", module_title, str(e))
    return {"context_text": "", "sources": []}


def generate_lesson(
    module_title: str,
    learning_goal: str,
    retriever: Optional[Callable[[str], Dict[str, Any]]],
) -> Dict[str, Any]:
    """Generate an interactive slide-based lesson for a single module.

    Builds a prompt grounded in RAG context (when available), calls the AI
    backend, and parses the JSON response. Falls back to a generic placeholder
    lesson if generation fails, the response is unparseable, or inputs are empty.

    Args:
        module_title: The title of the module to generate a lesson for.
        learning_goal: The learner's stated goal.
        retriever: A callable that accepts a query string and returns a dict
            with ``context_text`` and ``sources``, or None if unavailable.

    Returns:
        A dict with keys ``module_title`` (str), ``slides`` (list), and
        ``sources`` (list of source provenance dicts).
    """
    if not learning_goal or not learning_goal.strip():
        return _fallback_lesson(module_title)
    if not module_title or not module_title.strip():
        return _fallback_lesson("Untitled Module")

    rag_result = build_rag_context_for_module(module_title, learning_goal, retriever)
    rag_context = rag_result.get("context_text", "") if isinstance(rag_result, dict) else str(rag_result)
    sources = rag_result.get("sources", []) if isinstance(rag_result, dict) else []

    context_instruction = ""
    if rag_context and rag_context.strip():
        context_instruction = (
            "You MUST ground every slide in the provided Context below. "
            "Only state facts directly supported by the Context. "
            "If the Context is insufficient for a slide, write a general-education slide on the topic "
            "and label it as supplementary material — do NOT fabricate specific details, statistics, or examples "
            "not found in the Context.\n\n"
        )
    else:
        context_instruction = (
            "No source context is available. Write a general-education introduction to the topic. "
            "Use widely known facts only. Do NOT invent specific data, quotes, or statistics.\n\n"
        )

    prompt = f"""You are an expert educator creating a structured, interactive lesson for high-school to early-college learners.

{context_instruction}
Learning Goal: {learning_goal}
Module Title: {module_title}
Context: {rag_context if rag_context else 'No additional context available.'}

PEDAGOGICAL REQUIREMENTS:
1. Start with exactly 1-3 clear learning objectives on the first content slide.
2. Build concepts progressively: define basics before introducing complexity.
3. Every example slide must include a concrete, real-world scenario — not abstract descriptions.
4. The summary slide must recap learning objectives and key takeaways.
5. Use plain, jargon-free language. When a technical term is unavoidable, define it on first use.

{HUMOR_NOTE}
OUTPUT RULES:
- Respond with ONLY a JSON object — no prose, no markdown, no preamble.
- Every slide MUST have a "type" field that is exactly one of: title, content, example, summary.
- Content slides MUST have a "heading" (string) and "bullets" (array of strings, 2-5 items).
- Title slides MUST have "title" and "subtitle" (both strings).
- Example slides MUST have "heading" and "body" (both strings).
- Summary slides MUST have "bullets" (array of 2-5 strings).
- Generate exactly 6-8 slides.

JSON FORMAT:
{{
  "module_title": "{module_title}",
  "slides": [
    {{"type": "title", "title": "...", "subtitle": "..."}},
    {{"type": "content", "heading": "...", "bullets": ["...", "..."], "notes": "..."}},
    {{"type": "example", "heading": "...", "body": "..."}},
    {{"type": "summary", "bullets": ["...", "..."]}}
  ]
}}

Lesson:"""

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Lesson generation failed for module '%s': %s", module_title, str(e))
        return _fallback_lesson(module_title)

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)
            if 'slides' in result and isinstance(result['slides'], list):
                validated_slides = _validate_slides(result['slides'])
                if validated_slides:
                    return {
                        'module_title': result.get('module_title', module_title),
                        'slides': validated_slides,
                        'sources': sources,
                    }
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    return _fallback_lesson(module_title)


def _validate_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter slides to only include those with valid types.

    Args:
        slides: A list of slide dicts from AI output.

    Returns:
        Slides that have a valid ``type`` field (title/content/example/summary).
    """
    valid_types = {'title', 'content', 'example', 'summary'}
    validated = []
    for slide in slides:
        if isinstance(slide, dict) and slide.get('type', '') in valid_types:
            validated.append(slide)
    return validated


def _fallback_lesson(module_title: str) -> Dict[str, Any]:
    """Return a generic placeholder lesson when AI generation fails.

    Args:
        module_title: The module title to use in the fallback slides.

    Returns:
        A dict with ``module_title`` and a minimal set of placeholder slides.
    """
    return {
        'module_title': module_title,
        'slides': [
            {'type': 'title', 'title': module_title, 'subtitle': 'Lesson Content'},
            {'type': 'content', 'heading': 'Overview',
             'bullets': ['Review the provided materials for this module.',
                         'Focus on key concepts and terminology.',
                         'Practice with examples to reinforce understanding.'],
             'notes': ''},
            {'type': 'example', 'heading': 'Key Example',
             'body': 'Apply the concepts from this module to a practical scenario.'},
            {'type': 'summary', 'bullets': [
                'Review main concepts covered in this module.',
                'Ensure understanding before moving to the quiz.',
                'Retake the lesson if needed to master the material.'
            ]}
        ],
        'sources': [],
    }
