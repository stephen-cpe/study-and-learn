"""
Unit tests for the TTS audio generation service.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.services.tts_service import (
    _get_voice, generate_lesson_audio, get_audio_manifest,
    delete_lesson_audio, delete_module_audio,
    SPEAKER_VOICES, DEFAULT_VOICE, TTS_DIR,
)


def test_get_voice_returns_correct_neural_voice():
    assert _get_voice('Ava') == 'en-US-AvaNeural'
    assert _get_voice('Emma') == 'en-US-EmmaNeural'
    assert _get_voice('Ryan') == 'en-GB-RyanNeural'
    assert _get_voice('Andrew') == 'en-US-AndrewNeural'


def test_get_voice_returns_default_for_unknown():
    assert _get_voice('UnknownSpeaker') == DEFAULT_VOICE
    assert _get_voice('') == DEFAULT_VOICE


def test_generate_lesson_audio_creates_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)

    async def mock_generate_mp3(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('fake mp3 data')

    monkeypatch.setattr('src.services.tts_service._generate_mp3', mock_generate_mp3)

    script = [
        {'slide_index': -1, 'text': 'Hello! Welcome to the lesson.'},
        {'slide_index': 0, 'text': 'Let us begin with the first concept.'},
        {'slide_index': 1, 'text': 'Now we move to the next topic.'},
    ]

    manifest = generate_lesson_audio('path123', 0, script, 'Ava')

    assert manifest['path_id'] == 'path123'
    assert manifest['module_index'] == 0
    assert manifest['speaker'] == 'Ava'
    assert manifest['voice'] == 'en-US-AvaNeural'
    assert '-1' in manifest['slides']
    assert '0' in manifest['slides']
    assert '1' in manifest['slides']

    manifest_path = tmp_path / 'path123' / '0' / 'manifest.json'
    assert manifest_path.exists()
    saved = json.loads(manifest_path.read_text())
    assert saved['path_id'] == 'path123'

    assert (tmp_path / 'path123' / '0' / 'slide_0.mp3').exists()
    assert (tmp_path / 'path123' / '0' / 'slide_1.mp3').exists()
    assert (tmp_path / 'path123' / '0' / 'slide_2.mp3').exists()


def test_generate_lesson_audio_skips_empty_text(monkeypatch, tmp_path):
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)

    generated = []

    async def mock_generate_mp3(text, voice, out_path):
        generated.append(out_path.name)

    monkeypatch.setattr('src.services.tts_service._generate_mp3', mock_generate_mp3)

    script = [
        {'slide_index': -1, 'text': 'Hello!'},
        {'slide_index': 0, 'text': ''},
        {'slide_index': 1, 'text': '   '},
        {'slide_index': 2, 'text': 'Valid text here.'},
    ]

    manifest = generate_lesson_audio('path456', 0, script, 'Emma')

    assert len(generated) == 2
    assert 'slide_0.mp3' in generated
    assert 'slide_3.mp3' in generated
    assert '0' not in manifest['slides']
    assert '1' not in manifest['slides']


def test_delete_lesson_audio_removes_directory_tree(monkeypatch, tmp_path):
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)

    path_dir = tmp_path / 'path789'
    path_dir.mkdir(parents=True)
    (path_dir / '0' / 'slide_0.mp3').parent.mkdir(parents=True, exist_ok=True)
    (path_dir / '0' / 'slide_0.mp3').write_text('data')
    (path_dir / 'manifest.json').write_text('{}')

    assert path_dir.exists()

    delete_lesson_audio('path789')

    assert not path_dir.exists()
