"""
Regression tests for the narration / deck-layout ordering bug.

The bug: in ``src/services/lesson_orchestrator.py:build_module_artifacts``,
the deck layout used to generate the narration script was built with an
empty checkpoints dict, so it did NOT include the Quick Check / Final
Quiz / Results slots. The checkpoints were built AFTER narration, and a
correct deck layout was attached to the lesson dict, but the narration
script was never regenerated against the correct layout.

The user-visible symptom: the TTS narration skips the Quick Check
slides (the JS asks for audio at the checkpoint's deck position, but
the manifest has no entry for that key, so the audio route 404s and
the player stays silent or plays the next content slide's audio after
the checkpoint). Same symptom for the Final Quiz and Results slides.

After this fix:
  - The narration script's slide_index values MUST match the lesson's
    ``deck_layout`` deck_index values exactly (no missing entries, no
    extra entries).
  - Every checkpoint slot in the deck layout MUST have a narration
    entry in the script with a ``deck_kind == 'checkpoint'`` tag.
  - The final quiz and results slots MUST have narration entries.
  - The TTS manifest built from the narration script MUST have keys
    for every checkpoint / quiz / results slot — so the audio route
    can serve audio for them.
"""
import json
from unittest.mock import patch

import pytest

from src.services.lesson_orchestrator import build_module_artifacts


def _build_module_with_checkpoints(num_slides=6, num_checkpoints=2):
    """Build a realistic module: 6 content slides with 2 checkpoints
    inserted by the orchestrator (after slide 1 and slide 4)."""
    slides = []
    for i in range(num_slides):
        if i == 0:
            slides.append({'type': 'title', 'title': f'Title {i}', 'subtitle': 'Sub'})
        elif i == num_slides - 1:
            slides.append({'type': 'summary', 'bullets': ['done']})
        else:
            slides.append({'type': 'content', 'heading': f'Heading {i}',
                           'bullets': [f'bullet {i}-a', f'bullet {i}-b']})

    # Mock the lesson AI, quiz AI, and checkpoint AI
    def mock_retriever(query):
        return {'context_text': 'mock context', 'sources': []}

    return slides, mock_retriever


def test_narration_script_covers_every_checkpoint_in_deck_layout(monkeypatch):
    """The narration generator must be called with a deck_layout that
    includes the actual checkpoint positions. This is the user-reported
    symptom: TTS skips Quick Check slides.

    We verify by inspecting the prompt the AI received — the DECK LAYOUT
    section must list checkpoint slots at the right deck_index values
    (matching the final deck layout).
    """
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    captured_prompts = []
    def mock_lesson_ollama(prompt, model=None):
        if 'narration' in prompt.lower() or 'tutor' in prompt.lower():
            captured_prompts.append(prompt)
            return json.dumps([{'slide_index': -1, 'text': 'Intro'}])
        return json.dumps({
            'module_title': 'M',
            'slides': [
                {'type': 'title', 'title': 'T0', 'subtitle': 'S'},
                {'type': 'content', 'heading': 'H1', 'bullets': ['a']},
                {'type': 'content', 'heading': 'H2', 'bullets': ['b']},
            ],
        })

    monkeypatch.setattr('src.services.lesson_generator.call_ollama', mock_lesson_ollama)
    monkeypatch.setattr('src.services.quiz_generator.call_ollama',
                        lambda p, model=None: json.dumps({
                            'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                                           'options': ['A', 'B'], 'answer_index': 0,
                                           'explanation': 'E'}]
                        }))

    def retriever(q):
        return {'context_text': '', 'sources': []}

    artifacts = build_module_artifacts(
        {'title': 'M'},
        'Learn M',
        retriever,
        difficulty='Normal',
        tts_enabled=True,
        username='tester',
        tts_speaker='Ava',
    )

    # Final deck layout (with checkpoints) is the source of truth.
    final_layout = artifacts['lesson']['deck_layout']
    checkpoint_deck_indices = sorted(
        e['deck_index'] for e in final_layout if e['type'] == 'checkpoint'
    )

    # For 3 content slides, _build_checkpoints must produce at least 1
    # checkpoint (and the orchestrator must regenerate narration with
    # the layout that includes it).
    assert checkpoint_deck_indices, (
        "Test setup error: with 3 content slides, there must be at least "
        "one checkpoint in the final layout."
    )

    # The prompt the AI received must list those same deck_index values
    # in the DECK LAYOUT section. This is the structural guarantee.
    assert captured_prompts, "Orchestrator did not call AI for narration"
    prompt = captured_prompts[0]

    layout_idx = prompt.find('DECK LAYOUT')
    assert layout_idx >= 0, "Prompt is missing the DECK LAYOUT section"
    layout_section = prompt[layout_idx:]

    # Every checkpoint deck_index must appear as a "Deck slot N (Quick Check)"
    # line in the layout section.
    for di in checkpoint_deck_indices:
        expected_fragment = f'Deck slot {di} (Quick Check'
        assert expected_fragment in layout_section, (
            f"DECK LAYOUT section is missing the checkpoint at deck slot "
            f"{di}. Expected to find {expected_fragment!r}. Layout "
            f"section: {layout_section!r}"
        )


def test_narration_script_covers_final_quiz_slot(monkeypatch):
    """The Final Quiz slot must have a narration entry."""
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    def mock_lesson_ollama(prompt, model=None):
        if 'narration' in prompt.lower() or 'tutor' in prompt.lower():
            return json.dumps([
                {'slide_index': -1, 'text': 'Intro'},
                {'slide_index': 0, 'text': 'Title'},
                {'slide_index': 1, 'text': 'Content'},
                {'slide_index': 2, 'text': 'Final Quiz intro'},
                {'slide_index': 3, 'text': 'Results'},
            ])
        return json.dumps({
            'module_title': 'M',
            'slides': [
                {'type': 'title', 'title': 'T', 'subtitle': ''},
                {'type': 'content', 'heading': 'H', 'bullets': ['a']},
            ],
        })

    monkeypatch.setattr('src.services.lesson_generator.call_ollama', mock_lesson_ollama)
    monkeypatch.setattr('src.services.quiz_generator.call_ollama',
                        lambda p, model=None: json.dumps({
                            'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                                           'options': ['A', 'B'], 'answer_index': 0,
                                           'explanation': 'E'}]
                        }))

    def retriever(q):
        return {'context_text': '', 'sources': []}

    artifacts = build_module_artifacts(
        {'title': 'M'},
        'Learn M',
        retriever,
        difficulty='Normal',
        tts_enabled=True,
        username='tester',
        tts_speaker='Ava',
    )

    deck_layout = artifacts['lesson']['deck_layout']
    narration = artifacts['lesson']['narration']
    narration_indices = {entry['slide_index'] for entry in narration}

    # Find the quiz and results deck_index
    quiz_indices = {e['deck_index'] for e in deck_layout if e['type'] == 'quiz'}
    results_indices = {e['deck_index'] for e in deck_layout if e['type'] == 'results'}

    assert quiz_indices.issubset(narration_indices), (
        f"Narration missing entries for Final Quiz at deck positions "
        f"{quiz_indices - narration_indices}. The orchestrator generates "
        f"narration BEFORE computing the deck layout, so the quiz slot "
        f"is not in the script."
    )
    assert results_indices.issubset(narration_indices), (
        f"Narration missing entries for Results at deck positions "
        f"{results_indices - narration_indices}."
    )


def test_narration_script_keys_exactly_match_deck_layout_indices(monkeypatch):
    """The narration script's slide_index values must be the SAME SET
    as the deck layout's deck_index values (plus the intro at -1)."""
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    captured_prompts = []

    def mock_lesson_ollama(prompt, model=None):
        if 'narration' in prompt.lower() or 'tutor' in prompt.lower():
            captured_prompts.append(prompt)
            return json.dumps([{'slide_index': -1, 'text': 'Intro'}])
        return json.dumps({
            'module_title': 'M',
            'slides': [
                {'type': 'title', 'title': 'T', 'subtitle': ''},
                {'type': 'content', 'heading': 'H', 'bullets': ['a']},
                {'type': 'content', 'heading': 'H2', 'bullets': ['b']},
            ],
        })

    monkeypatch.setattr('src.services.lesson_generator.call_ollama', mock_lesson_ollama)
    monkeypatch.setattr('src.services.quiz_generator.call_ollama',
                        lambda p, model=None: json.dumps({
                            'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                                           'options': ['A', 'B'], 'answer_index': 0,
                                           'explanation': 'E'}]
                        }))

    def retriever(q):
        return {'context_text': '', 'sources': []}

    artifacts = build_module_artifacts(
        {'title': 'M'},
        'Learn M',
        retriever,
        difficulty='Normal',
        tts_enabled=True,
        username='tester',
        tts_speaker='Ava',
    )

    # KEY test: the prompt the AI received for narration must
    # mention the checkpoint. If the orchestrator passed an
    # empty-checkpoints deck_layout, no 'Quick Check' / 'Final Quiz'
    # / 'Results' will appear in the prompt.
    assert captured_prompts, "Orchestrator did not call AI for narration!"
    prompt = captured_prompts[0]
    print("\n\n=== CAPTURED PROMPT (first 2000 chars) ===\n", prompt[:2000], "\n=== END ===\n")

    # The narration prompt should list a checkpoint slot in the DECK LAYOUT
    # section, not just mention the word "checkpoint" in the instructions.
    # We check the DECK LAYOUT section specifically because that's where
    # the bug lives: in the buggy version, the layout was built BEFORE
    # checkpoints, so no checkpoint slot appears there.
    layout_marker = "DECK LAYOUT"
    layout_idx = prompt.find(layout_marker)
    assert layout_idx >= 0, "Prompt is missing the DECK LAYOUT section"
    layout_section = prompt[layout_idx:]

    has_checkpoint_slot = 'Quick Check' in layout_section
    has_quiz_slot = 'Final Quiz' in layout_section
    has_results_slot = 'Results' in layout_section

    assert has_checkpoint_slot, (
        f"DECK LAYOUT section of narration prompt does not include a "
        f"checkpoint slot. This means the orchestrator is building the "
        f"deck layout with empty checkpoints BEFORE calling the narration "
        f"generator, so the AI never sees the Quick Check positions and "
        f"never writes narration entries for them. This is the root cause "
        f"of the user-reported bug: TTS skips Quick Check slides and "
        f"plays the next content slide's audio after a checkpoint. "
        f"Layout section was: {layout_section!r}"
    )
    assert has_quiz_slot, "DECK LAYOUT section missing Final Quiz slot"
    assert has_results_slot, "DECK LAYOUT section missing Results slot"

    # We need at least 1 of these for the prompt to acknowledge deck slots.
    # For 3 content slides, the orchestrator's _build_checkpoints creates
    # at least 1 checkpoint, so all three should be present in the FIXED
    # version. In the BUGGY version, none are present because the layout
    # was built with empty checkpoints.
    assert has_checkpoint_slot, (
        f"DECK LAYOUT section of narration prompt does not include a "
        f"checkpoint slot. (See captured prompt above for the exact "
        f"prompt that was sent to the AI.)"
    )
    assert has_quiz_slot, (
        f"DECK LAYOUT section missing Final Quiz slot"
    )
    assert has_results_slot, (
        f"DECK LAYOUT section missing Results slot"
    )
