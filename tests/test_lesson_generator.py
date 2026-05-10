"""
Unit tests for the lesson generator service.
"""
import pytest
from app.services.lesson_generator import generate_lesson, _validate_slides, _fallback_lesson


def test_generate_lesson_with_mock(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    result = generate_lesson("Introduction to ML", "Learn machine learning", None)

    assert isinstance(result, dict)
    assert 'module_title' in result
    assert 'slides' in result
    assert isinstance(result['slides'], list)
    assert len(result['slides']) > 0


def test_generate_lesson_empty_goal(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    result = generate_lesson("Test Module", "", None)
    assert 'slides' in result
    assert len(result['slides']) > 0


def test_generate_lesson_empty_title(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    result = generate_lesson("", "Learn testing", None)
    assert 'module_title' in result


def test_generate_lesson_with_retriever(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    def mock_retrieve(query):
        return "Mock retrieved context"

    result = generate_lesson("ML Basics", "Learn ML", mock_retrieve)
    assert isinstance(result, dict)
    assert 'module_title' in result
    assert result['module_title'] == 'ML Basics'


def test_generate_lesson_prompt_construction(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import app.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "Intro", "slides": [{"type": "title", "title": "Intro", "subtitle": "Test"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("ML 101", "Learn ML", None)
    assert 'prompt' in captured_prompt
    assert 'ML 101' in captured_prompt['prompt']
    assert 'Learn ML' in captured_prompt['prompt']


def test_validate_slides():
    slides = [
        {"type": "title", "title": "Test"},
        {"type": "content", "heading": "H", "bullets": ["a"]},
        {"type": "unknown", "data": "ignored"},
        {"type": "summary", "bullets": ["done"]},
    ]
    valid = _validate_slides(slides)
    assert len(valid) == 3
    assert valid[0]['type'] == 'title'
    assert valid[1]['type'] == 'content'
    assert valid[2]['type'] == 'summary'


def test_fallback_lesson():
    result = _fallback_lesson("My Module")
    assert result['module_title'] == 'My Module'
    assert len(result['slides']) >= 3
    types = [s['type'] for s in result['slides']]
    assert 'title' in types
    assert 'content' in types
