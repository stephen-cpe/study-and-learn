"""Tests for Stage 1 tutor voice (tts_persona) and Stage 2 announcements."""
import json

from src.services.tts_announcement import build_announcement_text
from src.services.tts_persona import (
    build_tts_context_block,
    filter_memories_for_tts,
)


def test_filter_drops_voice_pref_and_prioritizes_struggle():
    mems = [
        {'memory_type': 'procedural', 'content': 'Prefers TTS voice Ava'},
        {'memory_type': 'episodic', 'content': "Passed quiz for 'Alpha' with 95%"},
        {'memory_type': 'semantic', 'content': "Struggling with 'Beta' — needs simpler review"},
        'Just a plain string memory',
    ]
    out = filter_memories_for_tts(mems, limit=5)
    assert all('Prefers TTS voice' not in m for m in out)
    # struggle first, then mastery
    assert 'Struggling' in out[0]
    assert any('Alpha' in m for m in out)


def test_filter_handles_strings_and_junk():
    assert filter_memories_for_tts(None) == []
    assert filter_memories_for_tts([]) == []
    out = filter_memories_for_tts(['  ', None, 123, 'Hello learner'])
    assert out == ['Hello learner']


def test_build_tts_context_includes_speaker_style():
    block = build_tts_context_block('Ryan', 'Bobby', 'Hard', ['Mastered X'])
    assert 'Ryan' in block
    assert 'Bobby' in block
    assert 'Mastered X' in block


def test_announcement_lesson_complete_with_suggestion():
    text = build_announcement_text(
        kind='lesson_complete', display_name='Bobby',
        module_title='Photosynthesis', score=90, passed=True,
        suggestion={'title': 'Cell Division', 'reason': 'It follows naturally.'},
    )
    assert 'Bobby' in text
    assert 'Photosynthesis' in text
    assert 'Cell Division' in text
    assert len(text) <= 400


def test_announcement_suggestion_without_title_falls_back():
    text = build_announcement_text(kind='suggestion', display_name='Ali', suggestion=None)
    assert 'Ali' in text or 'complete more modules' in text


def test_narration_prompt_uses_speaker_style(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    import src.services.lesson_generator as lg_module
    from src.services.lesson_orchestrator import build_deck_layout
    captured = {}

    def mock_call(prompt, model=None):
        captured['prompt'] = prompt
        return json.dumps([
            {'slide_index': -1, 'text': 'Hi!'},
            {'slide_index': 0, 'text': 'Welcome.'},
            {'slide_index': 1, 'text': 'Quiz.'},
            {'slide_index': 2, 'text': 'Done.'},
        ])

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call)
    slides = [{'type': 'title', 'title': 'Algebra', 'subtitle': 'Intro'}]
    layout = build_deck_layout(slides, {})
    lg_module.generate_narration_script(
        'Algebra', 'Alice', deck_layout=layout,
        learner_memories=[
            {'memory_type': 'procedural', 'content': 'Prefers TTS voice Ava'},
            {'memory_type': 'episodic', 'content': 'Mastered Fractions — ready for follow-ups'},
        ],
        tts_speaker='Ryan',
    )
    assert 'Ryan' in captured['prompt']
    assert 'Mastered Fractions' in captured['prompt']
    assert 'Prefers TTS voice' not in captured['prompt']


def test_announcement_audio_caches(monkeypatch, tmp_path):
    from src.services import tts_service as tts_module
    monkeypatch.setattr(tts_module, 'TTS_DIR', tmp_path)
    monkeypatch.setattr(tts_module, 'ANNOUNCE_DIR', tmp_path / 'announcements')

    calls = []

    async def mock_mp3(text, voice, out_path):
        calls.append(text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b'fake')

    monkeypatch.setattr(tts_module, '_generate_mp3', mock_mp3)
    r1 = tts_module.generate_announcement_audio('u1', 'Hello world', 'Ava')
    r2 = tts_module.generate_announcement_audio('u1', 'Hello world', 'Ava')
    assert r1['ann_id'] == r2['ann_id']
    assert r2['from_cache'] is True
    assert len(calls) == 1
    assert tts_module.get_announcement_path('u1', r1['ann_id']) is not None
    assert tts_module.get_announcement_path('u1', 'zzzz') is None
    assert tts_module.get_announcement_path('other', r1['ann_id']) is None
