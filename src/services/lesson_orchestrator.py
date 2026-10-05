"""
Lesson orchestration service — generates lesson slides, inline checkpoints,
and final quizzes for a single module.  Extracted from routes.py to keep
route handlers thin and testable.
"""
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

from src.services.lesson_generator import generate_lesson
from src.services.quiz_generator import generate_inline_checkpoint, generate_quiz
from src.services.rag_retriever import (
    build_rag_context,
    build_rag_context_from_hashes,
    build_rag_context_from_hashes_with_sources,
)
from src.services.settings_service import DEFAULT_DIFFICULTY, DEFAULT_TTS_SPEAKER

# Type alias for the canonical deck layout. Each entry is one slot in the
# rendered slide deck (content slide, checkpoint, final quiz, or results).
DeckLayoutEntry = Dict[str, Any]


# ── Content-status helpers (fail-closed degradation) ─────────────────────
#
# A "degraded" module is one whose lesson and/or quiz fell back to a
# placeholder. The quality audit found that quizzes are generated
# independently from RAG, so a degraded module can present an
# unanswerable quiz as graded material. These helpers let the routes,
# worker, and templates treat such modules as needing regeneration
# instead of silently counting them as taught-and-passable.

CONTENT_STATUS_READY = 'ready'
CONTENT_STATUS_DEGRADED = 'degraded'


def lesson_content_status(lesson: Dict[str, Any]) -> str:
    """Classify a persisted lesson dict as 'ready' or 'degraded'.

    Explicit flags are authoritative (``lesson.fallback`` /
    ``quiz.fallback``); the persisted ``content_status`` field wins when
    present so future reasons can be recorded without re-deriving.
    """
    if not isinstance(lesson, dict):
        return CONTENT_STATUS_DEGRADED
    status = lesson.get('content_status')
    if status == CONTENT_STATUS_DEGRADED:
        return CONTENT_STATUS_DEGRADED
    if status == CONTENT_STATUS_READY:
        return CONTENT_STATUS_READY
    if lesson.get('lesson', {}).get('fallback'):
        return CONTENT_STATUS_DEGRADED
    if lesson.get('quiz', {}).get('fallback'):
        return CONTENT_STATUS_DEGRADED
    return CONTENT_STATUS_READY


def is_lesson_degraded(lesson: Dict[str, Any]) -> bool:
    """True when a lesson dict's content failed to generate."""
    return lesson_content_status(lesson) == CONTENT_STATUS_DEGRADED


def build_deck_layout(
    slides: List[Dict[str, Any]],
    checkpoints: Dict[str, Any],
) -> List[DeckLayoutEntry]:
    """Build the canonical deck layout list.

    The deck is a flat sequence of slide elements. Content slides from
    ``slides`` are interleaved with their corresponding checkpoints
    (keyed by content index as string). The final quiz slide and the
    results slide are always the last two entries.

    Every entry has a unique ``deck_index`` (0..N) which the template
    uses as the ``data-deck-index`` attribute on the corresponding
    ``<section class="slide">``. Content slides additionally have
    ``content_index`` pointing back to their position in the source
    ``slides`` list. The narration script generator uses the same
    deck_index as its slide_index so the TTS manifest stays in sync
    with what the JS sees on the page.

    Args:
        slides: Source content slides (title/content/example/summary).
        checkpoints: Dict of {content_index_str: checkpoint_payload}.
            Keys are the stringified content_index, not the deck_index.

    Returns:
        A list of dicts, each with:
            - deck_index (int): unique sequential 0..N
            - type (str): one of 'content', 'checkpoint', 'quiz', 'results'
            - content_index (int | None): for content slides, the source
              slides index. None for quiz/results.
            - slide (dict | None): for content slides, the source slide dict.
            - checkpoint (dict | None): for checkpoint entries, the source
              checkpoint payload. None otherwise.
            - is_quiz (bool): True only for the final quiz entry.
            - is_results (bool): True only for the results entry.
    """
    layout: List[DeckLayoutEntry] = []
    deck_index = 0
    for content_index, slide in enumerate(slides):
        layout.append({
            'deck_index': deck_index,
            'type': 'content',
            'content_index': content_index,
            'slide': slide,
            'checkpoint': None,
            'is_quiz': False,
            'is_results': False,
        })
        deck_index += 1
        cp = checkpoints.get(str(content_index))
        if cp:
            layout.append({
                'deck_index': deck_index,
                'type': 'checkpoint',
                'content_index': content_index,
                'slide': None,
                'checkpoint': cp,
                'is_quiz': False,
                'is_results': False,
            })
            deck_index += 1
    # Final quiz slide
    layout.append({
        'deck_index': deck_index,
        'type': 'quiz',
        'content_index': None,
        'slide': None,
        'checkpoint': None,
        'is_quiz': True,
        'is_results': False,
    })
    deck_index += 1
    # Results slide
    layout.append({
        'deck_index': deck_index,
        'type': 'results',
        'content_index': None,
        'slide': None,
        'checkpoint': None,
        'is_quiz': False,
        'is_results': True,
    })
    return layout


def make_retriever(goal: str, extracted_texts: List[str]) -> Callable[[str], Dict[str, Any]]:
    """Build a simple retriever that returns RAG context for a query.

    Returns:
        A callable that accepts a query string and returns a dict with
        ``context_text`` (str) and ``sources`` (empty list — flat text
        mode has no ChromaDB source provenance).
    """
    def retrieve(query: str) -> Dict[str, Any]:
        text = build_rag_context(query or goal, extracted_texts) if extracted_texts else ""
        return {"context_text": text, "sources": []}
    return retrieve


def make_retriever_from_hashes(goal: str, file_hashes: List[str]) -> Callable[[str], Dict[str, Any]]:
    """Build a retriever that queries content-keyed ChromaDB collections.

    Returns:
        A callable that accepts a query string and returns a dict with
        ``context_text`` (str) and ``sources`` (list of source dicts with
        chunk_id, source_hash, score, text).
    """
    def retrieve(query: str) -> Dict[str, Any]:
        try:
            result = build_rag_context_from_hashes(query or goal, file_hashes)
            return result
        except Exception:
            return {"context_text": "", "sources": []}
    return retrieve


def make_retriever_from_hashes_with_names(
    goal: str,
    file_hashes: List[str],
    file_names: List[str],
    content_digest: str = "",
) -> Callable[[str], Dict[str, Any]]:
    """Build a retriever that returns sources with resolved filenames.

    Unlike ``make_retriever_from_hashes``, this variant also receives
    the original filenames so that source entries include human-readable
    filenames (rendering "my_notes.pdf" instead of a hash prefix).

    When ``content_digest`` is provided (the processing route's map-reduce
    digest of the entire document), it is prepended to every query result so
    the LLM is grounded in the full document even when similarity retrieval
    only surfaces a subset of chunks.

    Args:
        goal: The learning goal for context queries.
        file_hashes: SHA-256 file hashes.
        file_names: Original filenames, one per hash.
        content_digest: Full-coverage digest produced at processing time.

    Returns:
        Callable that returns dict with ``context_text`` and ``sources``.
        The callable accepts an optional ``exclude_chunks`` keyword arg
        (a set of chunk IDs to exclude from results) used by the
        cross-module dedup mechanism.
    """
    def retrieve(query: str, exclude_chunks: set = None) -> Dict[str, Any]:
        try:
            from config_defaults import (
                MODULE_CONTEXT_FRACTION_DEFAULT,
                MODULE_DIGEST_CHARS_DEFAULT,
                env_float,
                env_int,
            )
            from src.services.rag_budget import get_context_budget_chars
            # Reduced per-module context fraction (down from 0.35): the
            # audit tied the RMD parse failures to oversized module prompts,
            # where dense tables + the full digest + a large retrieval budget
            # pushed the model past reliable JSON emission. A smaller module
            # context trades marginal recall for a much higher valid-JSON rate.
            module_budget = get_context_budget_chars(fraction=env_float(
                'MODULE_CONTEXT_FRACTION', MODULE_CONTEXT_FRACTION_DEFAULT))
            result = build_rag_context_from_hashes_with_sources(
                query or goal, file_hashes, file_names,
                top_k=None, exclude_chunks=exclude_chunks,
                max_chars=module_budget,
            )
            if content_digest:
                # Truncate the digest per module: the summary/relevance
                # stages still receive the full digest from the route, but
                # the per-module lesson prompt keeps only the head so the
                # total prompt stays within a reliable JSON output budget.
                digest_cap = env_int(
                    'MODULE_DIGEST_CHARS', MODULE_DIGEST_CHARS_DEFAULT)
                digest_text = content_digest
                if digest_cap > 0 and len(digest_text) > digest_cap:
                    marker = '\n[... digest truncated for this module ...]'
                    digest_text = digest_text[:max(0, digest_cap - len(marker))] + marker
                digest_block = (
                    "# Complete Document Digest (every section)\n\n"
                    + digest_text
                    + "\n\n"
                )
                result["context_text"] = digest_block + result.get(
                    "context_text", ""
                )
            return result
        except Exception:
            return {"context_text": "", "sources": []}
    return retrieve


def build_module_artifacts(
    module: Dict[str, Any],
    learning_goal: str,
    retriever: Callable[[str], Dict[str, Any]],
    existing_slides: List[Dict[str, Any]] = None,
    difficulty: str = DEFAULT_DIFFICULTY,
    tts_enabled: bool = False,
    username: str = '',
    tts_speaker: str = DEFAULT_TTS_SPEAKER,
    next_module_title: str = None,
    is_last_module: bool = False,
    path_id: str = None,
    module_index: int = 0,
    used_chunk_ids: set = None,
    learner_memories: list = None,
    title_only: bool = False,
    covered_concepts: list = None,
    used_question_prompts: set = None,
) -> Dict[str, Any]:
    """
    Generate (or reuse) lesson slides, inline checkpoints, and a final quiz
    for a single module.

    Args:
        module: dict containing at least 'title'.
        learning_goal: the learner's stated goal.
        retriever: callable that accepts a query string and returns a dict
            with ``context_text`` and ``sources``.
        existing_slides: when provided, lesson generation is skipped and these
            slides are used directly (e.g. during a retake).
        difficulty: One of 'Easy', 'Normal', 'Hard'. Passed through to
            lesson, quiz, and checkpoint generators. Defaults to 'Normal'.
        tts_enabled: If True, generate narration script for the lesson.
        username: Learner's display name (for narration personalization).
        tts_speaker: TTS voice speaker name (e.g. 'Ava', 'Emma').
        next_module_title: Title of the next module (for outro preview).
        is_last_module: True if this is the final module.
        path_id: Study path ID (for TTS audio storage).
        module_index: Index of this module within the study path.
        used_chunk_ids: Set of chunk IDs already used by previous modules.
            Passed to the retriever to exclude already-used content, forcing
            each module to cover different document content. The set is
            mutated in-place — new chunk IDs from this module's retrieval
            are added so subsequent modules see them.
        learner_memories: Optional list of short strings or memory dicts
            about the learner (voice preference entries are filtered out
            by ``tts_persona``). Passed through to the narration
            generator for at-most-one natural callback.
        title_only: Forwarded to lesson generation — retrieve with the
            module title alone. Set for accepted follow-up topics so the
            new module teaches its own topic, not the original goal.
        covered_concepts: Titles/objectives of already-generated modules,
            forwarded to the lesson prompt as an explicit do-not-reteach
            list (concept-level cross-module dedup).
        used_question_prompts: Set of normalized quiz prompts already asked
            in this path. Forwarded to the quiz prompt as a do-not-repeat
            block; surviving prompts are added in-place so subsequent
            modules test fresh concepts (question-level cross-module
            dedup).

    Returns:
        dict with keys: 'lesson', 'quiz', 'checkpoints', 'sources'.
    """
    module_title = module.get("title", "")

    if existing_slides is not None:
        lesson_data = {"slides": existing_slides, "sources": []}
    else:
        lesson_data = generate_lesson(
            module_title, learning_goal, retriever,
            difficulty=difficulty,
            exclude_chunks=used_chunk_ids,
            title_only=title_only,
            covered_concepts=covered_concepts,
        )

    slides = lesson_data.get("slides", [])
    sources = lesson_data.get("sources", [])

    # Track chunk IDs used by this module so subsequent modules get
    # different content (cross-module dedup).
    if used_chunk_ids is not None:
        for src in sources:
            chunk_id = src.get("chunk_id", "") if isinstance(src, dict) else ""
            if chunk_id:
                used_chunk_ids.add(chunk_id)

    # Build checkpoints BEFORE the deck layout / narration. The deck
    # layout is the single source of truth for slide ordering and is
    # shared by the template, the JS, and the narration generator. If
    # we build narration before checkpoints, the script will not know
    # about the Quick Check / Final Quiz / Results deck slots, and the
    # TTS audio will be out of sync with what's on screen (the
    # user-reported symptom: "TTS skips Quick Check slides and plays
    # the next content slide's audio after a checkpoint").
    checkpoints = _build_checkpoints(slides, module_title, retriever, difficulty=difficulty)
    deck_layout = build_deck_layout(slides, checkpoints)

    if tts_enabled:
        from src.services.lesson_generator import generate_narration_script
        narration = generate_narration_script(
            module_title, username,
            next_module_title=next_module_title,
            is_last_module=is_last_module,
            difficulty=difficulty,
            deck_layout=deck_layout,
            learner_memories=learner_memories,
            tts_speaker=tts_speaker,
        )
        lesson_data['narration'] = narration
    else:
        lesson_data['narration'] = []

    from src.services.quiz_generator import _drop_repeated_questions
    avoid = sorted(used_question_prompts) if used_question_prompts else None
    quiz_data = generate_quiz(
        module_title, slides, retriever, n_questions=6,
        difficulty=difficulty, avoid_prompts=avoid,
    )
    if used_question_prompts is not None:
        # Post-filter: drop anything the prompt-level block missed, so a
        # repeated question can never ship. Quality over quantity: the
        # surviving distinct questions stand even if fewer than 6.
        kept = _drop_repeated_questions(
            quiz_data.get('questions', []), used_question_prompts)
        if kept:
            if len(kept) < len(quiz_data.get('questions', [])):
                logger.warning(
                    "Dropped %d cross-module duplicate quiz question(s) "
                    "for module '%s'",
                    len(quiz_data.get('questions', [])) - len(kept),
                    module_title,
                )
            quiz_data['questions'] = kept
        else:
            # Everything was a repeat (essentially impossible with the
            # prompt block active): keep the generated set so the module
            # still has a gradeable quiz, and record it.
            from src.services.quiz_generator import _normalize_question_prompt
            for q in quiz_data.get('questions', []):
                norm = _normalize_question_prompt((q or {}).get('prompt', ''))
                if norm:
                    used_question_prompts.add(norm)
    lesson_data['deck_layout'] = deck_layout

    return {
        "lesson": lesson_data,
        "quiz": quiz_data,
        "checkpoints": checkpoints,
        "sources": sources,
    }


def _build_checkpoints(
    slides: List[Dict[str, Any]],
    module_title: str,
    retriever: Callable[[str], Dict[str, Any]],
    difficulty: str = 'Normal',
) -> Dict[str, Any]:
    """Insert inline comprehension checkpoints at ~1/3 intervals."""
    checkpoints: Dict[str, Any] = {}
    if len(slides) > 2:
        interval = max(1, len(slides) // 3)
        for idx in range(interval - 1, len(slides) - 1, interval):
            slides_subset = slides[max(0, idx - 1) : idx + 1]
            cp = generate_inline_checkpoint(module_title, slides_subset, retriever, difficulty=difficulty)
            checkpoints[str(idx)] = cp
        if len(slides) > 1:
            last_checkpoint_slide = max(0, len(slides) - 2)
            if str(last_checkpoint_slide) not in checkpoints:
                slides_subset = slides[
                    max(0, last_checkpoint_slide - 1) : last_checkpoint_slide + 1
                ]
                cp = generate_inline_checkpoint(module_title, slides_subset, retriever, difficulty=difficulty)
                checkpoints[str(last_checkpoint_slide)] = cp
    return checkpoints
