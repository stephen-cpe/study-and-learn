"""
Lesson generation service for the Study-and-Learn MVP.

Generates RAG-grounded interactive slide-based lessons with four slide types:
title, content, example, and summary. Falls back to a generic placeholder
lesson when AI generation fails or returns unparseable output.
"""
import logging
from typing import Any, Callable, Dict, List, Optional

from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError
from src.services.prompts import DEFAULT_DIFFICULTY_INSTRUCTION, DIFFICULTY_INSTRUCTIONS

logger = logging.getLogger(__name__)


HUMOR_NOTE = (
    "TONE NOTE: For example slides only, a light-hearted analogy or a mildly "
    "absurd-but-fitting comparison is encouraged if it genuinely helps illustrate "
    "the concept. Never undermine the educational content. One well-placed wit per "
    "lesson is enough.\n"
)

MATH_NOTE = (
    "MATH NOTE: When a slide needs a mathematical formula or equation, write it "
    "as LaTeX wrapped in $...$ (inline) or $$...$$ (display) — e.g. "
    "$E=mc^2$ or $$\\sum_{i=1}^{n} x_i$$. Never use Unicode approximations "
    "(like ∑, √, ²) for real formulas. The deck renders LaTeX with KaTeX.\n"
)

NARRATION_MATH_NOTE = (
    "Speak any mathematics in plain words a listener can follow (e.g. "
    "\"E equals m c squared\") — NEVER emit LaTeX, dollar signs, or "
    "backslashes in narration text; it is read aloud by text-to-speech.\n"
)


def build_rag_context_for_module(
    module_title: str,
    learning_goal: str,
    retriever: Optional[Callable[[str], Dict[str, Any]]],
    exclude_chunks: set = None,
    title_only: bool = False,
) -> Dict[str, Any]:
    """Query the retriever for context relevant to a module.

    The query leads with the module title so similarity search favors
    the module's own topic; the learning goal follows for disambiguation.
    (Leading with the goal drowned the title and every module retrieved
    goal-level context, so accepted follow-up topics were taught with
    the original goal's content instead of their own.)

    Args:
        module_title: The module title to build a query around.
        learning_goal: The learner's stated goal.
        retriever: A callable that accepts a query string and returns a dict
            with ``context_text`` (str) and ``sources`` (list), or None.
        exclude_chunks: Optional set of chunk IDs to exclude from results
            (used by the cross-module dedup mechanism to prevent the same
            document content from appearing in multiple modules).
        title_only: When True, query with the module title alone. Used
            for accepted follow-up topics, which must be taught from
            their own topic's content rather than the original goal's.

    Returns:
        Dict with ``context_text`` (str) and ``sources`` (list).
    """
    try:
        if retriever:
            query = module_title if title_only else f"{module_title} {learning_goal}"
            kwargs = {}
            if exclude_chunks is not None:
                kwargs['exclude_chunks'] = exclude_chunks
            return retriever(query, **kwargs) or {"context_text": "", "sources": []}
    except Exception as e:
        logger.warning("RAG retrieval failed for module '%s': %s", module_title, str(e))
    return {"context_text": "", "sources": []}


def _build_lesson_prompt(
    module_title: str,
    learning_goal: str,
    rag_context: str,
    difficulty: str,
    covered_concepts: list = None,
) -> str:
    """Assemble the lesson generation prompt.

    Pure string assembly — no I/O, no retrieval — so it can be unit
    tested and tuned independently of ``generate_lesson``'s control flow.

    ``covered_concepts`` carries the titles/objectives of modules already
    generated in this path. Passing them with an explicit "do not re-teach"
    instruction addresses the cross-module repetition defect the audit
    found (all four AZ modules taught the same goal-level triad).
    """
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

    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DEFAULT_DIFFICULTY_INSTRUCTION)

    # Anti-fabrication: the audit found invented policy labels ("Rule of Two")
    # presented as document terminology. Prohibit coining names entirely.
    anti_fabrication = (
        "TERMINOLOGY RULE: Use ONLY names, labels, and acronyms that appear "
        "verbatim in the Context. Never invent or rename a rule, policy, "
        "framework, or procedure (do not coin labels like \"Rule of Two\"). "
        "If the Context does not name something, describe it without a "
        "proper name.\n\n"
    )

    # Cross-module dedup: when the earlier modules are known, forbid
    # re-teaching their concepts.
    covered_block = ""
    if covered_concepts:
        covered_lines = "\n".join(
            f"- {str(c).strip()[:120]}" for c in covered_concepts[:12]
            if str(c).strip()
        )
        if covered_lines:
            covered_block = (
                "ALREADY TAUGHT IN THIS COURSE (do NOT re-teach these "
                "topics — build on them instead):\n"
                f"{covered_lines}\n\n"
            )

    prompt = f"""You are an expert educator creating a structured, interactive lesson for high-school to early-college learners.

{context_instruction}
{diff_instruction}
{anti_fabrication}
{covered_block}Learning Goal: {learning_goal}
Module Title: {module_title}
Context: {rag_context if rag_context else 'No additional context available.'}

PEDAGOGICAL REQUIREMENTS:
1. Start with exactly 1-3 clear learning objectives on the first content slide.
2. Build concepts progressively: define basics before introducing complexity.
3. Every example slide must include a concrete, real-world scenario — not abstract descriptions.
4. The summary slide must recap learning objectives and key takeaways.
5. Use plain, jargon-free language. When a technical term is unavoidable, define it on first use.
6. CRITICAL: This module is part of a series. The Context provided is SPECIFIC to this module
   and is DIFFERENT from other modules' content. Teach ONLY what is in this module's Context.
   Do NOT repeat content from other modules — each module covers a distinct topic.

 {HUMOR_NOTE}
{MATH_NOTE}
OUTPUT RULES:
- Respond with ONLY a JSON object — no prose, no markdown, no preamble.
- Every slide MUST have a "type" field that is exactly one of: title, content, example, summary.
- Content slides MUST have a "heading" (string) and "bullets" (array of strings, 2-5 items).
- Title slides MUST have "title" and "subtitle" (both strings).
- Example slides MUST have "heading" and "body" (both strings).
- Summary slides MUST have "bullets" (array of 2-5 strings).
- Generate exactly 6 slides. Keep the JSON compact: bullets are short
  phrases, notes are optional and brief.

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
    return prompt


def generate_lesson(
    module_title: str,
    learning_goal: str,
    retriever: Optional[Callable[[str], Dict[str, Any]]],
    difficulty: str = 'Normal',
    exclude_chunks: set = None,
    title_only: bool = False,
    covered_concepts: list = None,
) -> Dict[str, Any]:
    """Generate an interactive slide-based lesson for a single module.

    Builds a prompt grounded in RAG context (when available), calls the AI
    backend, and parses the JSON response. Retries with a repair prompt on
    a parse/validation failure before degrading to a placeholder.

    Args:
        module_title: The title of the module to generate a lesson for.
        learning_goal: The learner's stated goal.
        retriever: A callable that accepts a query string and returns a dict
            with ``context_text`` and ``sources``, or None if unavailable.
        difficulty: One of 'Easy', 'Normal', 'Hard'. Controls vocabulary,
            sentence complexity, and depth. Defaults to 'Normal'.
        exclude_chunks: Optional set of chunk IDs to exclude from retrieval
            (prevents the same document content from repeating across modules).
        title_only: Forwarded to :func:`build_rag_context_for_module` —
            retrieve with the module title alone (accepted follow-ups).
        covered_concepts: Titles/objectives of modules already generated in
            this path; forwarded to the prompt as an explicit do-not-reteach
            list (concept-level cross-module dedup).

    Returns:
        A dict with keys ``module_title`` (str), ``slides`` (list), and
        ``sources`` (list of source provenance dicts).
    """
    if not learning_goal or not learning_goal.strip():
        return _fallback_lesson(module_title, degraded=True)
    if not module_title or not module_title.strip():
        return _fallback_lesson("Untitled Module", degraded=True)

    rag_result = build_rag_context_for_module(module_title, learning_goal, retriever, exclude_chunks=exclude_chunks,
                                              title_only=title_only)
    rag_context = rag_result.get("context_text", "") if isinstance(rag_result, dict) else str(rag_result)
    sources = rag_result.get("sources", []) if isinstance(rag_result, dict) else []

    prompt = _build_lesson_prompt(
        module_title=module_title,
        learning_goal=learning_goal,
        rag_context=rag_context,
        difficulty=difficulty,
        covered_concepts=covered_concepts,
    )

    from src.services.llm_json import generate_json, log_bad_response

    result = None
    try:
        result = generate_json(
            prompt,
            call_fn=call_ollama,
            parse_fn=_parse_lesson_response,
            schema_hint=_LESSON_SCHEMA_HINT,
            label=f"lesson:{module_title[:40]}",
        )
    except AIServiceError as e:
        # Backend error (not a parse failure): keep the historical
        # single retry, then degrade with the ai_error reason.
        logger.warning("Lesson generation attempt 1 failed for module '%s': %s — retrying once",
                       module_title, str(e))
        try:
            result = generate_json(
                prompt,
                call_fn=call_ollama,
                parse_fn=_parse_lesson_response,
                schema_hint=_LESSON_SCHEMA_HINT,
                label=f"lesson:{module_title[:40]}",
            )
        except AIServiceError as e2:
            logger.error("Lesson generation failed for module '%s': %s", module_title, str(e2))
            return _fallback_lesson(module_title, degraded=True, reason='ai_error')

    # ``generate_json`` returned a parsed object that still needs slide
    # validation; the repair loop treats a validation-empty result as a
    # parse failure only on the first pass, so re-check here.
    if result and 'slides' in result and isinstance(result['slides'], list):
        validated_slides = _fit_slide_count(
            _validate_slides(result['slides']),
            label=f"lesson:{module_title[:40]}",
        )
        if validated_slides:
            return {
                'module_title': result.get('module_title') or module_title,
                'slides': validated_slides,
                'sources': sources,
                'fallback': False,
            }

    log_bad_response(str(result), reason='lesson parse/validation', limit=1000)
    return _fallback_lesson(module_title, degraded=True, reason='parse_error')


# Schema description used by the repair prompt. Kept short — the repair
# re-prompt should not itself become a large generation.
_LESSON_SCHEMA_HINT = (
    '{"module_title": "<string>", "slides": ['
    '{"type": "title", "title": "...", "subtitle": "..."}, '
    '{"type": "content", "heading": "...", "bullets": ["...", "..."]}, '
    '{"type": "example", "heading": "...", "body": "..."}, '
    '{"type": "summary", "bullets": ["...", "..."]}]}'
)


def _parse_lesson_response(response: str):
    """Parse a lesson response and coerce it to a usable ``slides`` list.

    Returns None when the response has no usable slide content so the
    retry/repair loop treats it as a parse failure. Partial salvage: a
    response whose JSON parses but contains some malformed slides keeps
    the valid ones rather than discarding the whole module.
    """
    from src.services.llm_json import extract_json
    result = extract_json(response)
    if not isinstance(result, dict):
        return None
    slides = result.get('slides')
    if not isinstance(slides, list):
        return None
    valid = _fit_slide_count(
        _validate_slides(slides),
        label=f"lesson:{result.get('module_title', '')[:40]}",
    )
    if not valid:
        return None
    return {'module_title': result.get('module_title', ''), 'slides': valid}


def _validate_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter slides to only structurally usable ones.

    Unlike a bare type check, this drops slides missing their core fields so
    a single malformed slide cannot invalidate the whole module (partial
    salvage). A slide that survives here still renders on the deck.

    Args:
        slides: A list of slide dicts from AI output.

    Returns:
        Slides that have a valid ``type`` and their minimal fields.
    """
    valid_types = {'title', 'content', 'example', 'summary'}
    validated = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        stype = slide.get('type', '')
        if stype not in valid_types:
            continue
        # Minimal field presence per type.
        if stype == 'title' and not (
                slide.get('title') or slide.get('subtitle')):
            continue
        if stype == 'content' and not (
                slide.get('heading') or slide.get('bullets')):
            continue
        if stype == 'example' and not (
                slide.get('heading') or slide.get('body')):
            continue
        if stype == 'summary' and not slide.get('bullets'):
            continue
        validated.append(slide)
    return validated


#: Locked lesson length: the prompt asks for exactly 6 slides, and one
#: extra complete slide is tolerated when the topic needs the room (live
#: verification caught a 7-slide module with a complete arc). Anything
#: beyond that is trimmed, never silently dropped teaching content
#: without a log line.
MAX_SLIDES = 7


def _fit_slide_count(
    slides: List[Dict[str, Any]],
    label: str = "lesson",
    limit: int = MAX_SLIDES,
) -> List[Dict[str, Any]]:
    """Fit a validated slide list to the locked lesson length.

    Six or fewer slides pass through untouched (short-but-complete
    lessons are kept — the floor is enforced by the prompt, not by
    cutting). A 7th complete slide is accepted as-is. Beyond ``limit``,
    surplus middle slides are dropped so the lesson keeps its opening
    title and closing summary; the trim is logged.

    Args:
        slides: Validated slide dicts in deck order.
        label: Log prefix (usually the module title).
        limit: Maximum slides to keep.

    Returns:
        At most ``limit`` slides with the lesson arc preserved.
    """
    if len(slides) <= limit:
        return slides
    logger.warning(
        "%s: trimming %d slides to locked maximum %d",
        label, len(slides), limit,
    )
    head = slides[:1]
    tail: List[Dict[str, Any]] = []
    body = slides[1:]
    if body and body[-1].get('type') == 'summary':
        tail = body[-1:]
        body = body[:-1]
    # Preserve the arc: the worked example(s) survive; surplus middle
    # content slides are the ones dropped.
    keep_middle = limit - len(head) - len(tail)
    non_content = [s for s in body if s.get('type') != 'content']
    content_budget = max(0, keep_middle - len(non_content))
    middle: List[Dict[str, Any]] = []
    for s in body:
        if len(middle) >= keep_middle:
            break
        if s.get('type') == 'content':
            if content_budget > 0:
                middle.append(s)
                content_budget -= 1
        else:
            middle.append(s)
    return head + middle + tail


def _fallback_lesson(module_title: str, degraded: bool = False, reason: str = '') -> Dict[str, Any]:
    """Return a generic placeholder lesson when AI generation fails.

    Args:
        module_title: The module title to use in the fallback slides.
        degraded: When True, the returned dict carries ``'fallback': True``
            so callers (generation worker, lessons page) can surface that
            this module needs a retake instead of silently presenting
            placeholder slides as real content.
        reason: Machine-readable cause (``'ai_error'`` when the backend
            failed twice, ``'parse_error'`` when its response was not
            usable lesson JSON). Persisted on the lesson dict for later
            diagnosis; empty for direct-constructed fallbacks.

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
        'fallback': degraded,
        'fallback_reason': reason if degraded else '',
    }


def generate_narration_script(
    module_title: str,
    username: str,
    next_module_title: str = None,
    is_last_module: bool = False,
    difficulty: str = 'Normal',
    deck_layout: list = None,
    learner_memories: list = None,
    tts_speaker: str = 'Ava',
) -> list:
    """Generate a tutor-voice narration script for a lesson module.

    Makes one call_ollama() call per module to produce narration text.

    The script contains one entry per deck position (content slides,
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

    Fallback entries additionally carry a ``deck_kind`` field
    (``'content'``, ``'checkpoint'``, ``'quiz'``, ``'results'``) so
    consumers can reason about slot type without cross-referencing the
    layout.

    Args:
        module_title: The module title.
        username: The learner's display name.
        next_module_title: Title of the next module (for outro preview).
        is_last_module: True if this is the final module.
        difficulty: One of 'Easy', 'Normal', 'Hard'.
        deck_layout: The canonical deck layout list from
            ``build_deck_layout`` — the script is keyed by deck_index
            and includes entries for every deck slot (content,
            checkpoint, quiz, results).
        learner_memories: Optional list of short strings or
            ``{'memory_type':..., 'content':...}`` dicts describing what
            is known about the learner (TTS voice preference entries are
            filtered out). Passed through ``tts_persona`` filtering for
            at-most-one natural callback.
        tts_speaker: One of 'Ava', 'Emma', 'Ryan', 'Andrew'. Selects the
            tutor-voice style in the prompt (the voice itself is applied
            at synthesis time by ``tts_service``).

    Returns:
        List of dicts with 'slide_index' (int) and 'text' (str).
    """
    if deck_layout is None:
        deck_layout = []

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

    # Learner memory callback (TTS memory): at most one natural reference.
    # Memories live in the single MascotMemory table; tts_persona selects
    # narration-relevant ones (struggle/mastery first, voice-pref dropped).
    try:
        from src.services.tts_persona import (
            build_tts_context_block,
            filter_memories_for_tts,
        )
        filtered = filter_memories_for_tts(learner_memories or [], limit=5)
        tts_context_block = build_tts_context_block(
            speaker=tts_speaker or 'Ava',
            display_name=username,
            difficulty=difficulty,
            filtered_memories=filtered,
        )
        if filtered:
            learner_context_block = (
                "LEARNER CONTEXT (things we know about this learner):\n"
                + "\n".join(f"- {m.strip()}" for m in filtered)
                + "\nYou may reference at most ONE of these facts naturally in the "
                  "intro (-1) where genuinely relevant (e.g. a callback to a "
                  "module they passed). Never force it; never list facts.\n"
            )
        else:
            learner_context_block = ""
    except Exception:
        tts_context_block = ""
        memories = [m for m in (learner_memories or []) if isinstance(m, str) and m.strip()][:10]
        if memories:
            learner_context_block = (
                "LEARNER CONTEXT (things we know about this learner):\n"
                + "\n".join(f"- {m.strip()}" for m in memories)
                + "\nYou may reference at most ONE of these facts naturally in the "
                  "intro (-1) where genuinely relevant (e.g. a callback to a "
                  "module they passed). Never force it; never list facts.\n"
            )
        else:
            learner_context_block = ""

    prompt = f"""You are a friendly, enthusiastic tutor creating audio narration for an interactive lesson deck.
{tts_context_block}
The lesson is about: {module_title}.
{learner_context_block}
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
 - {NARRATION_MATH_NOTE}- RESPOND WITH ONLY a JSON array. No prose, no markdown.

JSON FORMAT:
[
  {{"slide_index": -1, "text": "Hello {username}! Today we are going to explore ..."}},
  {{"slide_index": 0, "text": "Let's start with ..."}},
  {{"slide_index": {last_index}, "text": "Great work! ..."}}
]
"""
    try:
        response = call_ollama(prompt)
        from src.services.llm_json import extract_json_array
        result = extract_json_array(response)
        if result and isinstance(result, list) and all('slide_index' in r and 'text' in r for r in result):
            return result
    except Exception as e:
        logger.warning("Narration script generation failed for '%s': %s", module_title, str(e))

    return _build_narration_fallback(
        module_title, username, is_last_module,
        deck_layout=deck_layout,
    )


def _build_narration_fallback(
    module_title, username, is_last_module,
    deck_layout: list = None,
):
    """Build a fallback narration script when the AI fails.

    The script has one entry per deck slot (content slides, checkpoints,
    quiz, results) plus intro at -1.
    """
    script = [{'slide_index': -1, 'text': f"Hello {username}! Today we are going to explore {module_title}. Let's get started."}]

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
