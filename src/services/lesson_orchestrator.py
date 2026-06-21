"""
Lesson orchestration service — generates lesson slides, inline checkpoints,
and final quizzes for a single module.  Extracted from routes.py to keep
route handlers thin and testable.
"""
from typing import Callable, Dict, Any, List

from src.services.rag_retriever import build_rag_context, build_rag_context_from_hashes_with_sources
from src.services.lesson_generator import generate_lesson
from src.services.quiz_generator import generate_quiz, generate_inline_checkpoint


# Type alias for the canonical deck layout. Each entry is one slot in the
# rendered slide deck (content slide, checkpoint, final quiz, or results).
DeckLayoutEntry = Dict[str, Any]


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
        text = build_rag_context(goal, extracted_texts) if extracted_texts else ""
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
            result = build_rag_context_from_hashes_with_sources(goal, file_hashes)
            return result
        except Exception:
            return {"context_text": "", "sources": []}
    return retrieve


def make_retriever_from_hashes_with_names(
    goal: str, file_hashes: List[str], file_names: List[str]
) -> Callable[[str], Dict[str, Any]]:
    """Build a retriever that returns sources with resolved filenames.

    Unlike ``make_retriever_from_hashes``, this variant also receives
    the original filenames so that source entries include human-readable
    filenames (rendering "my_notes.pdf" instead of a hash prefix).

    Args:
        goal: The learning goal for context queries.
        file_hashes: SHA-256 file hashes.
        file_names: Original filenames, one per hash.

    Returns:
        Callable that returns dict with ``context_text`` and ``sources``.
    """
    def retrieve(query: str) -> Dict[str, Any]:
        try:
            result = build_rag_context_from_hashes_with_sources(goal, file_hashes, file_names)
            return result
        except Exception:
            return {"context_text": "", "sources": []}
    return retrieve


def build_module_artifacts(
    module: Dict[str, Any],
    learning_goal: str,
    retriever: Callable[[str], Dict[str, Any]],
    existing_slides: List[Dict[str, Any]] = None,
    difficulty: str = 'Normal',
    tts_enabled: bool = False,
    username: str = '',
    tts_speaker: str = 'Ava',
    next_module_title: str = None,
    is_last_module: bool = False,
    path_id: str = None,
    module_index: int = 0,
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

    Returns:
        dict with keys: 'lesson', 'quiz', 'checkpoints', 'sources'.
    """
    module_title = module.get("title", "")

    if existing_slides is not None:
        lesson_data = {"slides": existing_slides, "sources": []}
    else:
        lesson_data = generate_lesson(module_title, learning_goal, retriever, difficulty=difficulty)

    slides = lesson_data.get("slides", [])
    sources = lesson_data.get("sources", [])

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
            module_title, slides, username,
            next_module_title=next_module_title,
            is_last_module=is_last_module,
            difficulty=difficulty,
            deck_layout=deck_layout,
        )
        lesson_data['narration'] = narration
    else:
        lesson_data['narration'] = []

    quiz_data = generate_quiz(module_title, slides, retriever, n_questions=5, difficulty=difficulty)
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
