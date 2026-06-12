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
            "id": "q4", "type": "cloze_dropdown", "prompt": "___ is the answer",
            "options": ["42", "7", "99", "0"], "answer_index": 0, "explanation": "Hitchhiker"
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
    types = ['mcq', 'true_false', 'cloze_dropdown']
    result = _build_type_mix(5, types)
    assert sum(result.values()) == 5
    assert result['mcq'] == 2
    assert result['true_false'] == 2
    assert result['cloze_dropdown'] == 1


def test_quiz_questions_have_explanations():
    result = _fallback_quiz(5)
    for q in result['questions']:
        assert 'explanation' in q, f"Question {q['id']} missing explanation"


def test_cloze_dropdown_validation():
    questions = [
        {
            "id": "q1", "type": "cloze_dropdown", "prompt": "The capital of France is ___.",
            "options": ["Paris", "Berlin", "Madrid", "London"], "answer_index": 0,
            "explanation": "Paris is the capital."
        },
        {
            "id": "q2", "type": "cloze_dropdown", "prompt": "___ is the process of learning.",
            "options": ["Studying", "Sleeping", "Eating", "Running"], "answer_index": 0,
            "explanation": "Studying is key."
        },
        {
            "id": "q3", "type": "cloze_dropdown", "prompt": "The answer is ___.",
            "options": ["42", "7", "99", "0"], "answer_index": 0,
            "explanation": "Ultimate answer."
        }
    ]
    valid = _validate_questions(questions, 3)
    assert len(valid) == 3
    for q in valid:
        assert q['type'] == 'cloze_dropdown'
        assert 'options' in q
        assert 'answer_index' in q
        assert len(q['options']) >= 3


def test_cloze_dropdown_in_fallback():
    result = _fallback_quiz(5)
    cd_q = None
    for q in result['questions']:
        if q['type'] == 'cloze_dropdown':
            cd_q = q
            break
    assert cd_q is not None
    assert 'options' in cd_q
    assert 'answer_index' in cd_q
    assert len(cd_q['options']) >= 3


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
    assert 'cloze_dropdown' in p or 'cloze dropdown' in p.lower()


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
        if q['type'] == 'cloze_dropdown':
            assert 'options' in q, f"Cloze dropdown must have options: {q['id']}"
            assert 'answer_index' in q, f"Cloze dropdown must have answer_index: {q['id']}"
            assert len(q['options']) >= 3, f"Cloze dropdown must have at least 3 options: {q['id']}"


def test_cloze_dropdown_grading_correct():
    from src.services.grader import _grade_single_question
    question = {
        'id': 'q1', 'type': 'cloze_dropdown',
        'prompt': 'The capital of France is ___.',
        'options': ['Paris', 'Berlin', 'Madrid', 'London'],
        'answer_index': 0, 'explanation': 'Paris is the capital.'
    }
    assert _grade_single_question(question, 0) is True


def test_cloze_dropdown_grading_wrong():
    from src.services.grader import _grade_single_question
    question = {
        'id': 'q1', 'type': 'cloze_dropdown',
        'prompt': 'The capital of France is ___.',
        'options': ['Paris', 'Berlin', 'Madrid', 'London'],
        'answer_index': 0, 'explanation': 'Paris is the capital.'
    }
    assert _grade_single_question(question, 1) is False


def test_cloze_dropdown_options_shuffled():
    from src.services.quiz_generator import _shuffle_questions
    questions = [{
        'id': 'q1', 'type': 'cloze_dropdown',
        'prompt': 'Water is ___.',
        'options': ['H2O', 'CO2', 'NaCl', 'O2'],
        'answer_index': 0, 'explanation': 'Water is H2O.'
    }]
    shuffled = _shuffle_questions(questions)
    q = shuffled[0]
    assert q['type'] == 'cloze_dropdown'
    assert 'H2O' in q['options']
    assert q['options'][q['answer_index']] == 'H2O'


def test_legacy_fill_blank_graded_as_mcq():
    from src.services.grader import _grade_single_question
    question = {
        'id': 'q1', 'type': 'fill_blank',
        'prompt': 'The capital of France is ___.',
        'options': ['Paris', 'Berlin', 'Madrid', 'London'],
        'answer_index': 0, 'explanation': 'Paris is the capital.'
    }
    assert _grade_single_question(question, 0) is True
    assert _grade_single_question(question, 1) is False


def test_checkpoint_mcq_type(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    slides = [
        {"type": "content", "heading": "Intro", "bullets": ["Point A", "Point B"]}
    ]
    result = generate_inline_checkpoint("Test", slides, None, cp_type='mcq')
    assert isinstance(result, dict)
    assert result['type'] == 'mcq'
    assert 'prompt' in result
    assert 'options' in result
    assert len(result['options']) >= 2
    assert 'answer_index' in result
    assert 'explanation' in result


def test_checkpoint_true_false_type(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.quiz_generator as qg_module

    def mock_call_ollama(prompt, model=None):
        return '{"id": "cp", "type": "true_false", "prompt": "The sky is blue.", "answer": true, "explanation": "Rayleigh scattering makes the sky appear blue."}'

    monkeypatch.setattr(qg_module, 'call_ollama', mock_call_ollama)

    slides = [
        {"type": "content", "heading": "Intro", "bullets": ["Point A", "Point B"]}
    ]
    result = generate_inline_checkpoint("Test", slides, None, cp_type='true_false')
    assert isinstance(result, dict)
    assert result['type'] == 'true_false'
    assert 'prompt' in result
    assert 'answer' in result
    assert isinstance(result['answer'], bool)
    assert 'explanation' in result


def test_checkpoint_cloze_dropdown_type(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.quiz_generator as qg_module

    def mock_call_ollama(prompt, model=None):
        return '{"id": "cp", "type": "cloze_dropdown", "prompt": "The chemical symbol for water is ___.", "options": ["H2O", "CO2", "NaCl", "O2"], "answer_index": 0, "explanation": "Water is H2O."}'

    monkeypatch.setattr(qg_module, 'call_ollama', mock_call_ollama)

    slides = [
        {"type": "content", "heading": "Intro", "bullets": ["Point A", "Point B"]}
    ]
    result = generate_inline_checkpoint("Test", slides, None, cp_type='cloze_dropdown')
    assert isinstance(result, dict)
    assert result['type'] == 'cloze_dropdown'
    assert 'prompt' in result
    assert '___' in result['prompt']
    assert 'options' in result
    assert len(result['options']) >= 3
    assert 'answer_index' in result
    assert 'explanation' in result


def test_quiz_prompt_contains_humor_instructions(monkeypatch):
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

    assert 'HUMOR REQUIREMENT' in p
    assert 'ridiculous' in p.lower()
    assert 'classroom-appropriate' in p.lower()
