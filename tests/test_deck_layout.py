"""
Tests for the deck layout (Task 4 — Bug #2 fix).

After Task 4:
  - Every deck slide element (content, checkpoint, quiz, results) has a
    unique data-deck-index attribute.
  - Content slides additionally carry data-content-index.
  - The narration script is keyed by deck index (0..N+1) and includes
    one entry per deck slide — including checkpoint, quiz, and results.
  - Intro is at -1, outro is at the results slide's deck index.
  - The deck layout is exposed as lesson['deck_layout'] for the template.
"""
import json
import pytest

from src.services.lesson_orchestrator import build_deck_layout
from src.services.lesson_generator import (
    generate_narration_script,
    _build_narration_fallback,
)


# ── Deck layout builder ───────────────────────────────────────────────

def test_deck_layout_assigns_unique_deck_indices():
    """Every element in the deck (content + checkpoint + quiz + results)
    must have a unique deck_index."""
    slides = [
        {'type': 'title', 'title': 'T1', 'subtitle': ''},
        {'type': 'content', 'heading': 'C1', 'bullets': ['a']},
        {'type': 'content', 'heading': 'C2', 'bullets': ['b']},
        {'type': 'summary', 'bullets': ['done']},
    ]
    # One checkpoint after content slide 1 (deck position 1)
    checkpoints = {
        '1': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0},
    }
    layout = build_deck_layout(slides, checkpoints)
    deck_indices = [e['deck_index'] for e in layout]
    # Must be unique
    assert len(deck_indices) == len(set(deck_indices)), (
        f"Deck indices not unique: {deck_indices}"
    )
    # Must be sequential starting at 0
    assert deck_indices == list(range(len(deck_indices)))


def test_deck_layout_orders_content_then_checkpoint():
    """A checkpoint at content_index=1 must appear at the deck position
    immediately after the content slide with content_index=1 (matching the
    existing template convention where checkpoints follow their anchor slide)."""
    slides = [
        {'type': 'title', 'title': 'T0', 'subtitle': ''},
        {'type': 'content', 'heading': 'C0', 'bullets': ['a']},
        {'type': 'content', 'heading': 'C1', 'bullets': ['b']},
    ]
    checkpoints = {
        '1': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0},
    }
    layout = build_deck_layout(slides, checkpoints)
    # Strip quiz + results for the position check.
    content_or_cp = [e for e in layout if e['type'] in ('content', 'checkpoint')]
    # Expect: content 0 (di=0), content 1 (di=1), checkpoint for ci=1 (di=2)
    assert content_or_cp[0]['type'] == 'content'
    assert content_or_cp[0]['deck_index'] == 0
    assert content_or_cp[0]['content_index'] == 0
    assert content_or_cp[1]['type'] == 'content'
    assert content_or_cp[1]['deck_index'] == 1
    assert content_or_cp[1]['content_index'] == 1
    assert content_or_cp[2]['type'] == 'checkpoint'
    assert content_or_cp[2]['deck_index'] == 2
    assert content_or_cp[2]['content_index'] == 1


def test_deck_layout_no_checkpoints_when_dict_empty():
    """When checkpoints is empty, the layout has only content slides
    (plus the always-present quiz + results slots at the end)."""
    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    layout = build_deck_layout(slides, {})
    # Total = 2 content + 1 quiz + 1 results = 4
    assert len(layout) == 4
    content_entries = [e for e in layout if e['type'] == 'content']
    assert len(content_entries) == 2
    assert all(e['type'] == 'content' for e in content_entries)
    assert [e['deck_index'] for e in content_entries] == [0, 1]
    assert [e['content_index'] for e in content_entries] == [0, 1]


def test_deck_layout_includes_quiz_and_results():
    """Quiz and results slides are the last two entries in the layout."""
    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    layout = build_deck_layout(slides, {})
    # Last is results, second-to-last is quiz
    assert layout[-1]['type'] == 'results'
    assert layout[-2]['type'] == 'quiz'
    assert layout[-1]['deck_index'] == 3
    assert layout[-2]['deck_index'] == 2


def test_deck_layout_strict_type_set():
    """Every entry must be one of content/checkpoint/quiz/results."""
    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    checkpoints = {
        '0': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0},
    }
    layout = build_deck_layout(slides, checkpoints)
    valid_types = {'content', 'checkpoint', 'quiz', 'results'}
    for entry in layout:
        assert entry['type'] in valid_types, f"Invalid type: {entry['type']}"


def test_deck_layout_preserves_checkpoint_payload():
    """The checkpoint payload (prompt, options, type, answer_index) must be
    carried through to the layout entry so the template and narration can use it."""
    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    cp = {
        'type': 'true_false',
        'prompt': 'Is X true?',
        'answer': True,
    }
    checkpoints = {'0': cp}
    layout = build_deck_layout(slides, checkpoints)
    cp_entry = [e for e in layout if e['type'] == 'checkpoint'][0]
    assert cp_entry['checkpoint'] is cp


# ── Narration script (deck-aware) ────────────────────────────────────

def test_narration_script_includes_one_entry_per_deck_position():
    """The narration script must have one entry per deck position (plus intro at -1),
    including checkpoint, quiz, and results entries — not just content slides."""
    import src.services.lesson_generator as lg_module
    captured = {}

    def mock_call(prompt, model=None):
        captured['prompt'] = prompt
        return json.dumps([
            {'slide_index': -1, 'text': 'Hello!'},
            {'slide_index': 0, 'text': 'Title narration.'},
            {'slide_index': 1, 'text': 'Checkpoint narration.'},
            {'slide_index': 2, 'text': 'Content 1 narration.'},
            {'slide_index': 3, 'text': 'Final quiz narration.'},
            {'slide_index': 4, 'text': 'Results narration.'},
        ])

    lg_module.call_ollama = mock_call

    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    checkpoints = {
        '0': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0},
    }
    layout = build_deck_layout(slides, checkpoints)
    # layout has 4 entries: content 0, checkpoint, content 1, quiz, results
    # So deck indices 0..4 (5 entries) plus intro at -1.
    script = generate_narration_script('M', slides, 'Alice', deck_layout=layout)
    deck_indices = [e['slide_index'] for e in script]
    assert -1 in deck_indices, "Missing intro entry"
    # All deck positions from 0..len(layout)-1 must be present
    for i in range(len(layout)):
        assert i in deck_indices, (
            f"Narration missing entry for deck position {i}: {deck_indices}"
        )


def test_narration_script_checkpoint_entry_uses_short_tutor_voice():
    """The prompt must instruct the AI to write a short tutor-voice narration
    for checkpoint slides (not read the question)."""
    import src.services.lesson_generator as lg_module
    captured = {}

    def mock_call(prompt, model=None):
        captured['prompt'] = prompt
        return json.dumps([
            {'slide_index': -1, 'text': 'Hi!'},
            {'slide_index': 0, 'text': 'T.'},
            {'slide_index': 1, 'text': 'Quick check!'},
            {'slide_index': 2, 'text': 'Final quiz.'},
            {'slide_index': 3, 'text': 'Results.'},
        ])

    lg_module.call_ollama = mock_call
    slides = [{'type': 'title', 'title': 'T', 'subtitle': ''}]
    layout = build_deck_layout(slides, {'0': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0}})
    generate_narration_script('M', slides, 'Alice', deck_layout=layout)
    p = captured['prompt']
    # Checkpoint narration must be instructed to be short and encouraging
    assert 'checkpoint' in p.lower()
    assert 'test your understanding' in p.lower() or 'quick check' in p.lower()


def test_narration_script_quiz_entry_introduces_final_quiz():
    """The final-quiz narration entry must mention that the learner is about
    to take a final quiz."""
    import src.services.lesson_generator as lg_module
    captured = {}

    def mock_call(prompt, model=None):
        captured['prompt'] = prompt
        return json.dumps([
            {'slide_index': -1, 'text': 'Hi!'},
            {'slide_index': 0, 'text': 'T.'},
            {'slide_index': 1, 'text': 'Content.'},
            {'slide_index': 2, 'text': 'Final quiz.'},
            {'slide_index': 3, 'text': 'Results.'},
        ])

    lg_module.call_ollama = mock_call
    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    layout = build_deck_layout(slides, {})
    generate_narration_script('M', slides, 'Alice', deck_layout=layout)
    p = captured['prompt']
    # The prompt must include a "final quiz" instruction for the AI.
    assert 'final quiz' in p.lower()


def test_narration_script_results_entry_references_results():
    """The results narration entry must reference showing the learner's results."""
    import src.services.lesson_generator as lg_module
    captured = {}

    def mock_call(prompt, model=None):
        captured['prompt'] = prompt
        return json.dumps([
            {'slide_index': -1, 'text': 'Hi!'},
            {'slide_index': 0, 'text': 'T.'},
            {'slide_index': 1, 'text': 'Q.'},
            {'slide_index': 2, 'text': 'Results.'},
        ])

    lg_module.call_ollama = mock_call
    slides = [{'type': 'title', 'title': 'T', 'subtitle': ''}]
    layout = build_deck_layout(slides, {})
    generate_narration_script('M', slides, 'Alice', deck_layout=layout)
    p = captured['prompt']
    assert 'results' in p.lower()


def test_narration_script_fallback_uses_deck_layout_when_provided():
    """When the AI fails, the fallback must also use the deck layout to
    produce one entry per deck position (with sensible per-type fallback text)."""
    import src.services.lesson_generator as lg_module

    def mock_call_raises(prompt, model=None):
        from src.services.exceptions import AIServiceError
        raise AIServiceError('Simulated failure')

    lg_module.call_ollama = mock_call_raises

    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    checkpoints = {
        '0': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0},
    }
    layout = build_deck_layout(slides, checkpoints)
    script = generate_narration_script('M', slides, 'Alice', deck_layout=layout)
    deck_indices = sorted([e['slide_index'] for e in script])
    expected = [-1] + list(range(len(layout)))
    assert deck_indices == expected, (
        f"Fallback narration missing deck entries. Got {deck_indices}, expected {expected}"
    )


def test_narration_fallback_for_checkpoint_uses_gentle_text():
    """The fallback for a checkpoint slide should be a short, encouraging line
    (NOT a reading of the question)."""
    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    checkpoints = {
        '0': {'type': 'mcq', 'prompt': 'P?', 'options': ['A', 'B'], 'answer_index': 0},
    }
    layout = build_deck_layout(slides, checkpoints)
    fallback = _build_narration_fallback('M', slides, 'Alice', None, False, deck_layout=layout)
    cp_entry = [e for e in fallback if e.get('deck_kind') == 'checkpoint'][0]
    # Should be short and NOT include the literal question prompt
    assert len(cp_entry['text']) < 100
    assert 'P?' not in cp_entry['text']


def test_narration_fallback_for_quiz_uses_intro_text():
    """The fallback for the final quiz slide should be an encouraging intro."""
    slides = [{'type': 'title', 'title': 'T', 'subtitle': ''}]
    layout = build_deck_layout(slides, {})
    fallback = _build_narration_fallback('M', slides, 'Alice', None, False, deck_layout=layout)
    quiz_entry = [e for e in fallback if e.get('deck_kind') == 'quiz'][0]
    assert 'quiz' in quiz_entry['text'].lower() or 'test' in quiz_entry['text'].lower()


def test_narration_fallback_for_results_uses_results_text():
    """The fallback for the results slide should reference the results."""
    slides = [{'type': 'title', 'title': 'T', 'subtitle': ''}]
    layout = build_deck_layout(slides, {})
    fallback = _build_narration_fallback('M', slides, 'Alice', None, False, deck_layout=layout)
    results_entry = [e for e in fallback if e.get('deck_kind') == 'results'][0]
    assert 'results' in results_entry['text'].lower() or 'how you did' in results_entry['text'].lower()


# ── Orchestrator integration ─────────────────────────────────────────

def test_build_module_artifacts_attaches_deck_layout():
    """build_module_artifacts must attach the deck_layout to the lesson dict
    so the template can iterate over it instead of building the layout itself."""
    from src.services.lesson_orchestrator import build_module_artifacts

    slides = [
        {'type': 'title', 'title': 'T', 'subtitle': ''},
        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
    ]
    # Use the flat-text retriever (no RAG context)
    def retriever(q):
        return {'context_text': '', 'sources': []}

    artifacts = build_module_artifacts(
        {'title': 'Test Module'},
        'Learn X',
        retriever,
        difficulty='Normal',
        tts_enabled=False,
    )
    assert 'deck_layout' in artifacts['lesson']
    layout = artifacts['lesson']['deck_layout']
    assert isinstance(layout, list)
    assert len(layout) >= 3  # at least: 2 content + quiz + results
    types = [e['type'] for e in layout]
    assert 'quiz' in types
    assert 'results' in types


def test_build_module_artifacts_deck_layout_indices_unique():
    """deck_layout deck_index values must be unique sequential integers."""
    from src.services.lesson_orchestrator import build_module_artifacts

    def retriever(q):
        return {'context_text': '', 'sources': []}

    artifacts = build_module_artifacts(
        {'title': 'M'},
        'Learn M',
        retriever,
        difficulty='Normal',
        tts_enabled=False,
    )
    layout = artifacts['lesson']['deck_layout']
    indices = [e['deck_index'] for e in layout]
    assert indices == list(range(len(indices))), (
        f"deck_index not sequential 0..N: {indices}"
    )


# ── Audio sync (TTS manifest compatibility) ──────────────────────────

def test_tts_manifest_keys_match_deck_indices():
    """TTS service must build the manifest with deck_index keys
    (not content slide indices), so the audio route can serve them by deck index."""
    from src.services.tts_service import generate_lesson_audio
    import tempfile
    import pathlib

    with tempfile.TemporaryDirectory() as temp_dir:
        tmp_path = pathlib.Path(temp_dir)
        script = [
            {'slide_index': -1, 'text': 'Intro'},
            {'slide_index': 0, 'text': 'Slide 0'},
            {'slide_index': 1, 'text': 'Checkpoint'},
            {'slide_index': 2, 'text': 'Slide 1'},
        ]

        async def mock_gen(text, voice, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text('fake')

        import src.services.tts_service as tts
        original_dir = tts.TTS_DIR
        tts.TTS_DIR = tmp_path
        tts._generate_mp3 = mock_gen
        try:
            manifest = generate_lesson_audio('pathX', 0, script, 'Ava')
        finally:
            tts.TTS_DIR = original_dir

        # The manifest must have entries for -1, 0, 1, 2 — the deck indices.
        assert '-1' in manifest['slides']
        assert '0' in manifest['slides']
        assert '1' in manifest['slides']
        assert '2' in manifest['slides']
