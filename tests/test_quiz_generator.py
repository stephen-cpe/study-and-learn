"""
Unit tests for the quiz generator service.
"""
import pytest
from src.services.quiz_generator import (
    generate_quiz, generate_inline_checkpoint, _validate_questions,
    _fallback_quiz, _summarize_slides, _build_type_mix
)


def test_generate_quiz_with_mock(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    result = generate_quiz("Test Module", [], None, n_questions=5)
    assert isinstance(result, dict)
    assert 'questions' in result
    assert isinstance(result['questions'], list)
    assert len(result['questions']) == 5


def test_generate_quiz_empty_title(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    result = generate_quiz("", [], None)
    assert 'questions' in result
    assert len(result['questions']) > 0


def test_generate_quiz_with_retriever(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    def mock_retrieve(query):
        return "Mock context for quiz"

    result = generate_quiz("ML Quiz", [], mock_retrieve, n_questions=3)
    assert len(result['questions']) == 3


def test_generate_inline_checkpoint_with_mock(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    slides = [
        {"type": "content", "heading": "Intro", "bullets": ["Point A", "Point B"]}
    ]
    result = generate_inline_checkpoint("Test", slides, None)
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'prompt' in result
    assert 'options' in result
    assert 'answer_index' in result


def test_generate_inline_checkpoint_with_retriever(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    def mock_retrieve(query):
        return "More context"

    result = generate_inline_checkpoint("Unit 1", [], mock_retrieve)
    assert isinstance(result, dict)
    assert 'prompt' in result


def test_validate_questions():
    questions = [
        {
            "id": "q1", "type": "mcq", "prompt": "What is X?",
            "options": ["A", "B", "C", "D"], "answer_index": 2, "explanation": "Because"
        },
        {
            "id": "q2", "type": "true_false", "prompt": "Is X true?",
            "answer": True, "explanation": "Yes"
        },
        {
            "id": "q3", "type": "multi_select", "prompt": "Select all",
            "options": ["A", "B", "C"], "answer_indices": [0, 1], "explanation": "Both"
        },
        {
            "id": "q4", "type": "fill_blank", "prompt": "___ is the answer",
            "answer": "42", "acceptable_answers": ["42", "forty two"], "explanation": "Hitchhiker"
        },
        {
            "id": "q5", "type": "invalid", "prompt": "bad"
        }
    ]
    valid = _validate_questions(questions, 5)
    assert len(valid) == 4


def test_fallback_quiz():
    result = _fallback_quiz(3)
    assert len(result['questions']) == 3


def test_fallback_quiz_default_count():
    result = _fallback_quiz()
    assert len(result['questions']) == 5


def test_summarize_slides():
    slides = [
        {"type": "title", "title": "T1"},
        {"type": "content", "heading": "H1", "bullets": ["b1", "b2"]},
        {"type": "example", "body": "example text"},
    ]
    summary = _summarize_slides(slides)
    assert 'T1' in summary
    assert 'b1' in summary
    assert 'example text' in summary


def test_build_type_mix():
    types = ['mcq', 'true_false', 'fill_blank']
    result = _build_type_mix(5, types)
    assert sum(result.values()) == 5
    assert result['mcq'] == 2
    assert result['true_false'] == 2
    assert result['fill_blank'] == 1


def test_quiz_questions_have_explanations():
    result = _fallback_quiz(5)
    for q in result['questions']:
        assert 'explanation' in q, f"Question {q['id']} missing explanation"
