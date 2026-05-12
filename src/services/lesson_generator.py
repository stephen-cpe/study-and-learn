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

    prompt = f"""You are an AI assistant that creates interactive lessons.
Generate a structured lesson for the following module, grounded in the provided context.

Learning Goal: {learning_goal}
Module Title: {module_title}
Context: {rag_context if rag_context else 'No additional context available.'}

Create 6-8 slides covering the key concepts for this module. Include:
- A title slide
- Content slides with headings and bullet points
- At least one example slide
- A summary slide

Provide your response in the following JSON format:
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
