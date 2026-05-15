"""
Lesson generation service for the Study-and-Learn MVP.
"""
import json
from src.services.ai_client import call_ollama


def build_rag_context_for_module(module_title: str, learning_goal: str, retriever) -> str:
    try:
        if retriever:
            query = f"{learning_goal} {module_title}"
            return retriever(query) or ""
    except Exception:
        pass
    return ""


def generate_lesson(module_title: str, learning_goal: str, retriever) -> dict:
    if not learning_goal or not learning_goal.strip():
        return _fallback_lesson(module_title)
    if not module_title or not module_title.strip():
        return _fallback_lesson("Untitled Module")

    rag_context = build_rag_context_for_module(module_title, learning_goal, retriever)

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

    response = call_ollama(prompt)

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
                        'slides': validated_slides
                    }
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    return _fallback_lesson(module_title)


def _validate_slides(slides: list) -> list:
    valid_types = {'title', 'content', 'example', 'summary'}
    validated = []
    for slide in slides:
        if isinstance(slide, dict) and slide.get('type', '') in valid_types:
            validated.append(slide)
    return validated


def _fallback_lesson(module_title: str) -> dict:
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
        ]
    }
