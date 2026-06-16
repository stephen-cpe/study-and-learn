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

DIFFICULTY_INSTRUCTIONS = {
    'Easy': (
        "AUDIENCE — Easy (age 10–11):\n"
        "Use short sentences and simple vocabulary. Introduce every concept with a "
        "concrete everyday analogy before stating the formal definition. Avoid jargon "
        "entirely — if a technical term is unavoidable, define it immediately in plain "
        "language. Use encouraging language. Never condescend; treat the learner as "
        "curious and fully capable.\n"
    ),
    'Normal': (
        "AUDIENCE — Normal (age 12–13):\n"
        "Use clear, moderately detailed language. Some subject-specific terms are "
        "appropriate — define each on first use before continuing. Assume the learner "
        "has basic school-level knowledge. Balance depth with accessibility.\n"
    ),
    'Hard': (
        "AUDIENCE — Hard (age 14–15):\n"
        "Use full subject vocabulary without simplifying. Do not filter or dumb down "
        "material. Assume a motivated learner who can handle nuance, multi-step "
        "reasoning, and precise terminology. Keep examples concise and sophisticated.\n"
    ),
}


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
    difficulty: str = 'Normal',
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
        difficulty: One of 'Easy', 'Normal', 'Hard'. Controls vocabulary,
            sentence complexity, and depth. Defaults to 'Normal'.

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

    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DIFFICULTY_INSTRUCTIONS['Normal'])

    prompt = f"""You are an expert educator creating a structured, interactive lesson for high-school to early-college learners.

{context_instruction}
{diff_instruction}
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


def generate_narration_script(
    module_title: str,
    slides: list,
    username: str,
    next_module_title: str = None,
    is_last_module: bool = False,
    difficulty: str = 'Normal',
    deck_layout: list = None,
) -> list:
    """Generate a tutor-voice narration script for a lesson module.

    Makes one call_ollama() call per module to produce narration text.

    When ``deck_layout`` is provided (the new contract from Task 4), the
    script contains one entry per deck position (content slides,
    checkpoints, final quiz, and results) plus an intro at ``-1``. The
    ``slide_index`` of each entry matches the corresponding
    ``deck_index`` in the layout, so the TTS manifest stays in sync with
    what the JS sees on the page. Each entry's ``text`` is tutor-voice
    narration tailored to the slot type:

        - Content slides: 2–4 sentences explaining the slide.
        - Checkpoint slides: short, encouraging prompt to think and
          answer. Does NOT read the question aloud.
        - Final quiz slide: announces the upcoming quiz and encourages
          the learner.
        - Results slide: acknowledges the learner and previews pass/fail
          (the actual verdict is rendered by the page itself).

    When ``deck_layout`` is None (legacy / back-compat), the script
    contains entries only for content slides (one per slide, indexed
    0..N-1) plus intro at -1 and outro at N. This preserves the
    behavior of the old contract for callers that haven't migrated.

    Stored as a list of dicts ``{'slide_index': int, 'text': str}`` plus
    a ``deck_kind`` field for fallback entries (``'intro'``,
    ``'content'``, ``'checkpoint'``, ``'quiz'``, ``'results'``,
    ``'outro'``) so consumers can reason about slot type without
    cross-referencing the layout.

    Args:
        module_title: The module title.
        slides: List of slide dicts from the lesson.
        username: The learner's display name.
        next_module_title: Title of the next module (for outro preview).
        is_last_module: True if this is the final module.
        difficulty: One of 'Easy', 'Normal', 'Hard'.
        deck_layout: Optional canonical deck layout list. When provided,
            the script is keyed by deck_index and includes entries for
            every deck slot (content, checkpoint, quiz, results).

    Returns:
        List of dicts with 'slide_index' (int) and 'text' (str).
    """
    if deck_layout is None:
        return _generate_narration_legacy(
            module_title, slides, username, next_module_title,
            is_last_module, difficulty,
        )

    layout_descriptions = []
    for entry in deck_layout:
        di = entry['deck_index']
        kind = entry['type']
        if kind == 'content':
            slide = entry.get('slide') or {}
            stype = slide.get('type', '')
            if stype == 'title':
                body = f"{slide.get('title', '')} — {slide.get('subtitle', '')}"
            elif stype == 'content':
                bullets = ' | '.join(slide.get('bullets', []))
                body = f"{slide.get('heading', '')} — {bullets}"
            elif stype == 'example':
                body = f"{slide.get('heading', '')} — {slide.get('body', '')}"
            elif stype == 'summary':
                bullets = ' | '.join(slide.get('bullets', []))
                body = bullets
            else:
                body = ''
            layout_descriptions.append(
                f"Deck slot {di} (content slide, type={stype}): {body}"
            )
        elif kind == 'checkpoint':
            cp = entry.get('checkpoint') or {}
            cp_type = cp.get('type', 'mcq')
            prompt_text = cp.get('prompt', '')
            layout_descriptions.append(
                f"Deck slot {di} (Quick Check, type={cp_type}): A short "
                f"comprehension question about the previous slide(s). "
                f"DO NOT read the question prompt '{prompt_text}' aloud — "
                f"instead, write a short encouraging tutor prompt (max 40 words) "
                f"asking the learner to think about what they just learned."
            )
        elif kind == 'quiz':
            layout_descriptions.append(
                f"Deck slot {di} (Final Quiz): The learner is now at the end "
                f"of the lesson. Write a short, encouraging intro (max 50 words) "
                f"that announces the final quiz and reassures the learner that "
                f"they can retake it if needed. Do NOT read the actual quiz "
                f"questions — those are visible on the page."
            )
        elif kind == 'results':
            layout_descriptions.append(
                f"Deck slot {di} (Results): The learner just finished the quiz. "
                f"Write a short narration (max 50 words) acknowledging the "
                f"completion and encouraging them — pass or fail, this is a "
                f"learning moment. Do NOT predict the score; the page renders "
                f"the actual pass/fail verdict."
            )
    layout_text = '\n'.join(layout_descriptions)
    last_index = deck_layout[-1]['deck_index']
    outro_instruction = (
        f"For deck slot {last_index} (Results): the outro is the Results slot itself. "
        f"{'Congratulate the learner on completing ' + module_title + ' (this is the final module of the course). ' if is_last_module else 'Briefly preview the next module: ' + (next_module_title or 'the next topic') + '. '}"
        f"Encourage them — pass or fail, learning is the goal."
    )

    prompt = f"""You are a friendly, enthusiastic tutor creating audio narration for an interactive lesson deck.
The learner's name is {username}. The lesson is about: {module_title}.
Difficulty: {difficulty}.

The deck is a sequence of slots, each with its own deck_index. The JS player
plays audio for the active slot. You must produce exactly one narration
entry per deck slot, using the slot's deck_index as the slide_index in
your JSON output. The slot types are:

- content: a normal lesson slide (title/content/example/summary).
  Write 2–4 natural spoken sentences that explain, connect, and elaborate
  (max 60 words). Do NOT just read the bullets aloud.
- checkpoint: an inline Quick Check that blocks the learner from advancing
  until they answer. Write a short, encouraging tutor prompt (max 40 words)
  that invites them to think about the question. Do NOT read the question
  text aloud — the question is already shown on the slide.
- quiz: the Final Quiz slide. Write a short, encouraging intro (max 50
  words) announcing the quiz and reassuring the learner. Do NOT read the
  actual questions.
- results: the post-quiz results slide. Write a short narration (max 50
  words) acknowledging completion and encouraging the learner. Do NOT
  predict the score.

ALSO write an intro entry with slide_index=-1: 2 sentences. Address
{username} by name. Introduce the topic enthusiastically.

DECK LAYOUT (one narration per slot, indexed by deck_index):
{layout_text}

OTHER INSTRUCTIONS:
- {outro_instruction}
- Use analogies, transitions, and conversational language appropriate for
  the difficulty level.
- RESPOND WITH ONLY a JSON array. No prose, no markdown.

JSON FORMAT:
[
  {{"slide_index": -1, "text": "Hello {username}! Today we are going to explore ..."}},
  {{"slide_index": 0, "text": "Let's start with ..."}},
  {{"slide_index": {last_index}, "text": "Great work! ..."}}
]
"""
    try:
        response = call_ollama(prompt)
        start = response.find('[')
        end = response.rfind(']') + 1
        if start != -1 and end > start:
            result = json.loads(response[start:end])
            if isinstance(result, list) and all('slide_index' in r and 'text' in r for r in result):
                return result
    except Exception as e:
        logger.warning("Narration script generation failed for '%s': %s", module_title, str(e))

    return _build_narration_fallback(
        module_title, slides, username, next_module_title, is_last_module,
        deck_layout=deck_layout,
    )


def _generate_narration_legacy(
    module_title, slides, username, next_module_title, is_last_module, difficulty,
) -> list:
    """Legacy narration generator (back-compat). Produces one entry per
    content slide, indexed 0..N-1, plus intro at -1 and outro at N.

    Used by callers that haven't been migrated to the deck_layout contract.
    """
    slide_contents = []
    for i, slide in enumerate(slides):
        stype = slide.get('type', '')
        if stype == 'title':
            slide_contents.append(f"Slide {i} (title): {slide.get('title','')} — {slide.get('subtitle','')}")
        elif stype == 'content':
            bullets = ' | '.join(slide.get('bullets', []))
            slide_contents.append(f"Slide {i} (content): {slide.get('heading','')} — {bullets}")
        elif stype == 'example':
            slide_contents.append(f"Slide {i} (example): {slide.get('heading','')} — {slide.get('body','')}")
        elif stype == 'summary':
            bullets = ' | '.join(slide.get('bullets', []))
            slide_contents.append(f"Slide {i} (summary): {bullets}")

    slides_text = '\n'.join(slide_contents)
    outro_instruction = (
        f"For the outro (slide_index={len(slides)}): "
        f"{'Congratulate the learner on completing ' + module_title + ' and suggest they explore a related topic next.' if is_last_module else 'Briefly preview the next lesson: ' + (next_module_title or 'the next topic') + '.'}"
    )

    prompt = f"""You are a friendly, enthusiastic tutor creating audio narration for a lesson.
The learner's name is {username}. The lesson is about: {module_title}.
Difficulty: {difficulty}.

Here are the lesson slides:
{slides_text}

Write a narration script. For EACH slide, write 2–4 natural spoken sentences that:
1. Do NOT just read the bullets aloud — explain, connect, and elaborate as a tutor would.
2. Use analogies, transitions, and conversational language appropriate for the difficulty level.
3. Keep each slide narration concise (max 60 words).

Also write:
- An intro (slide_index=-1): 2 sentences. Address {username} by name. Introduce the topic enthusiastically.
- {outro_instruction}

RESPOND WITH ONLY a JSON array. No prose, no markdown.
FORMAT:
[
  {{"slide_index": -1, "text": "Hello {username}! Today we are going to explore ..."}},
  {{"slide_index": 0, "text": "Let's start with ..."}},
  {{"slide_index": {len(slides)}, "text": "Great work! ..."}}
]
"""
    try:
        response = call_ollama(prompt)
        start = response.find('[')
        end = response.rfind(']') + 1
        if start != -1 and end > start:
            result = json.loads(response[start:end])
            if isinstance(result, list) and all('slide_index' in r and 'text' in r for r in result):
                return result
    except Exception as e:
        logger.warning("Legacy narration script generation failed for '%s': %s", module_title, str(e))

    return _build_narration_fallback(
        module_title, slides, username, next_module_title, is_last_module,
    )


def _build_narration_fallback(
    module_title, slides, username, next_module_title, is_last_module,
    deck_layout: list = None,
):
    """Build a fallback narration script when the AI fails.

    When ``deck_layout`` is provided, the script has one entry per deck
    slot (content slides, checkpoints, quiz, results) plus intro at -1.
    When ``deck_layout`` is None, falls back to the legacy layout: one
    entry per content slide plus intro at -1 and outro at len(slides).
    """
    script = [{'slide_index': -1, 'text': f"Hello {username}! Today we are going to explore {module_title}. Let's get started."}]
    if deck_layout is None:
        # Legacy: one entry per content slide
        for i, slide in enumerate(slides):
            stype = slide.get('type', '')
            parts = []
            if stype == 'title':
                parts.append(slide.get('title', ''))
                if slide.get('subtitle'): parts.append(slide['subtitle'])
            elif stype == 'content':
                if slide.get('heading'): parts.append(slide.get('heading', '') + '.')
                parts.extend(slide.get('bullets', []))
            elif stype == 'example':
                if slide.get('heading'): parts.append(slide.get('heading', '') + '.')
                if slide.get('body'): parts.append(slide.get('body', ''))
            elif stype == 'summary':
                parts.append('To summarize:')
                parts.extend(slide.get('bullets', []))
            text = ' '.join(p.strip() for p in parts if p.strip())
            if text:
                script.append({'slide_index': i, 'text': text})
        # Outro at len(slides)
        if is_last_module:
            outro = f"Congratulations on completing {module_title}! Well done."
        elif next_module_title:
            outro = f"Great work on {module_title}! Next, we will explore {next_module_title}."
        else:
            outro = f"That wraps up {module_title}. Well done!"
        script.append({'slide_index': len(slides), 'text': outro})
        return script

    # Deck-aware fallback: one entry per deck slot, plus intro at -1
    for entry in deck_layout:
        di = entry['deck_index']
        kind = entry['type']
        if kind == 'content':
            slide = entry.get('slide') or {}
            stype = slide.get('type', '')
            parts = []
            if stype == 'title':
                parts.append(slide.get('title', ''))
                if slide.get('subtitle'): parts.append(slide.get('subtitle', ''))
            elif stype == 'content':
                if slide.get('heading'): parts.append(slide.get('heading', '') + '.')
                parts.extend(slide.get('bullets', []))
            elif stype == 'example':
                if slide.get('heading'): parts.append(slide.get('heading', '') + '.')
                if slide.get('body'): parts.append(slide.get('body', ''))
            elif stype == 'summary':
                parts.append('To summarize:')
                parts.extend(slide.get('bullets', []))
            text = ' '.join(p.strip() for p in parts if p.strip())
            if not text:
                text = f"Moving on to the next part of {module_title}."
            script.append({'slide_index': di, 'text': text, 'deck_kind': 'content'})
        elif kind == 'checkpoint':
            # Short, encouraging tutor prompt — does NOT read the question
            text = f"Quick check time! Take a moment to answer this question about {module_title}."
            script.append({'slide_index': di, 'text': text, 'deck_kind': 'checkpoint'})
        elif kind == 'quiz':
            text = f"Final quiz time — answer all questions to complete {module_title}. You can retake it if you need to."
            script.append({'slide_index': di, 'text': text, 'deck_kind': 'quiz'})
        elif kind == 'results':
            if is_last_module:
                text = f"Here's how you did on the final quiz for {module_title}! Every step counts."
            else:
                text = f"Here's how you did on {module_title}! Don't worry if you need a retake — that's how learning works."
            script.append({'slide_index': di, 'text': text, 'deck_kind': 'results'})
    return script
