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


def test_fill_blank_validation_rejects_multi_word():
    questions = [
        {
            "id": "q1", "type": "fill_blank", "prompt": "The capital of France is __.",
            "answer": "paris", "acceptable_answers": ["paris", "france"],
            "explanation": "Paris is the capital."
        },
        {
            "id": "q2", "type": "fill_blank", "prompt": "___ is the process of learning.",
            "answer": "study", "acceptable_answers": ["study", "active recall", "memorization technique"],
            "explanation": "Studying is key."
        },
        {
            "id": "q3", "type": "fill_blank", "prompt": "The answer is __.",
            "answer": "42",
            "explanation": "Ultimate answer."
        }
    ]
    valid = _validate_questions(questions, 3)
    assert len(valid) == 3

    # q1: all single-word entries kept
    assert len(valid[0]['acceptable_answers']) == 2
    assert 'paris' in valid[0]['acceptable_answers']
    assert 'france' in valid[0]['acceptable_answers']

    # q2: multi-word "active recall" and "memorization technique" filtered out
    assert len(valid[1]['acceptable_answers']) == 1
    assert valid[1]['acceptable_answers'] == ['study']

    # q3: no acceptable_answers provided, falls back to answer
    assert len(valid[2]['acceptable_answers']) == 1
    assert valid[2]['acceptable_answers'] == ['42']


def test_fill_blank_answer_is_single_word_in_fallback():
    result = _fallback_quiz(5)
    fb_q = None
    for q in result['questions']:
        if q['type'] == 'fill_blank':
            fb_q = q
            break
    assert fb_q is not None
    assert ' ' not in fb_q['answer'], f"Fill-blank answer '{fb_q['answer']}' must be a single word"
    for a in fb_q['acceptable_answers']:
        assert ' ' not in a, f"Acceptable answer '{a}' must be a single word"


def test_quiz_prompt_requires_plausible_distractors(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.quiz_generator as qg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Test?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    monkeypatch.setattr(qg_module, 'call_ollama', mock_call_ollama)

    generate_quiz("Test Module", [], None, n_questions=3)
    p = captured_prompt['prompt']

    assert 'plausible' in p.lower()
    assert 'distractor' in p.lower() or 'wrong answer' in p.lower()
    assert 'single word' in p.lower()
    assert 'fill_blank' in p or 'fill blank' in p.lower()


def test_quiz_prompt_contains_pedagogical_requirements(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.quiz_generator as qg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Test?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    monkeypatch.setattr(qg_module, 'call_ollama', mock_call_ollama)

    generate_quiz("Biology 101", [], None, n_questions=3)
    p = captured_prompt['prompt']

    assert 'explanation' in p.lower()
    assert 'unambiguously' in p.lower() or 'unambiguous' in p.lower()
    assert 'MUST' in p
    assert 'only a JSON' in p.lower() or 'ONLY a JSON' in p


def test_quiz_prompt_rag_grounding_with_context(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.quiz_generator as qg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Test?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    monkeypatch.setattr(qg_module, 'call_ollama', mock_call_ollama)

    def mock_retrieve(query):
        return "Mitochondria produce ATP through cellular respiration."

    generate_quiz("Cell Biology", [], mock_retrieve, n_questions=3)
    p = captured_prompt['prompt']

    assert 'MUST base' in p or 'base every' in p.lower()
    assert 'fabricate' in p.lower() or 'NOT' in p or 'do NOT' in p


def test_checkpoint_prompt_uses_immediate_recall(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.quiz_generator as qg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"id": "cp", "type": "mcq", "prompt": "Test?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}'

    monkeypatch.setattr(qg_module, 'call_ollama', mock_call_ollama)

    slides = [{"type": "content", "heading": "Mitosis", "bullets": ["Cells divide", "DNA replicates"]}]
    generate_inline_checkpoint("Biology", slides, None)
    p = captured_prompt['prompt']

    assert 'IMMEDIATE RECALL' in p or 'immediate recall' in p.lower()
    assert 'core concept' in p.lower() or 'key concept' in p.lower()
    assert 'NOT obscure' in p or 'not obscure' in p.lower()
    assert 'plausible' in p.lower()


def test_mock_responses_pass_validation_under_new_prompts(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    quiz = generate_quiz("Test Module", [], None, n_questions=5)
    assert isinstance(quiz, dict)
    assert 'questions' in quiz
    assert len(quiz['questions']) == 5
    for q in quiz['questions']:
        assert 'type' in q
        assert 'prompt' in q
        assert 'explanation' in q
        if q['type'] == 'fill_blank':
            assert ' ' not in q['answer'], f"Fill-blank answer must be single word: {q['answer']}"
            for a in q.get('acceptable_answers', []):
                assert ' ' not in a, f"Acceptable answer must be single word: {a}"
