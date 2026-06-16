"""
Unit tests for the lesson generator service.
"""
import pytest
from src.services.lesson_generator import (
    generate_lesson, _validate_slides, _fallback_lesson,
    generate_narration_script, _build_narration_fallback,
)


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

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "Intro", "slides": [{"type": "title", "title": "Intro", "subtitle": "Test"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("ML 101", "Learn ML", None)
    assert 'prompt' in captured_prompt
    assert 'ML 101' in captured_prompt['prompt']
    assert 'Learn ML' in captured_prompt['prompt']


def test_lesson_prompt_contains_pedagogical_constraints(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "Test", "slides": [{"type": "title", "title": "Test", "subtitle": "S"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Biology 101", "Learn cell biology", None)
    p = captured_prompt['prompt']

    assert 'learning objectives' in p.lower()
    assert 'progressive' in p.lower() or 'progressively' in p.lower()
    assert 'real-world' in p.lower() or 'concrete' in p.lower()
    assert 'summary' in p.lower()
    assert 'JSON' in p
    assert 'ground' in p.lower() or 'MUST' in p or 'only' in p.lower()


def test_lesson_prompt_contains_rag_grounding_when_context_present(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "Test", "slides": [{"type": "title", "title": "Test", "subtitle": "S"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    def mock_retrieve(query):
        return "Cells have a nucleus and cytoplasm."

    generate_lesson("Cell Biology", "learn cells", mock_retrieve)
    p = captured_prompt['prompt']

    assert 'MUST ground' in p or 'ground every' in p.lower()
    assert 'fabricate' in p.lower() or 'NOT' in p or 'do NOT' in p


def test_lesson_prompt_no_context_graceful_fallback(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "Test", "slides": [{"type": "title", "title": "Test", "subtitle": "S"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Math 101", "Learn algebra", None)
    p = captured_prompt['prompt']

    assert 'No source context' in p or 'general-education' in p.lower()
    assert 'widely known' in p.lower() or 'do NOT invent' in p


def test_lesson_prompt_json_output_constraints(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "T", "slides": [{"type": "title", "title": "T", "subtitle": "T"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Physics", "Learn mechanics", None)
    p = captured_prompt['prompt']

    assert 'ONLY a JSON object' in p or 'no prose' in p.lower()
    assert 'type' in p


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


def test_lesson_prompt_contains_humor_note(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "T", "slides": [{"type": "title", "title": "T", "subtitle": "T"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Physics", "Learn mechanics", None)
    p = captured_prompt['prompt']

    assert 'TONE NOTE' in p
    assert 'light-hearted' in p.lower() or 'absurd' in p.lower()
    assert 'example slides' in p.lower()


def test_lesson_prompt_difficulty_easy(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "T", "slides": [{"type": "title", "title": "T", "subtitle": "T"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Physics", "Learn mechanics", None, difficulty='Easy')
    p = captured_prompt['prompt']

    assert 'AUDIENCE — Easy' in p
    assert 'age 10–11' in p
    assert 'simple vocabulary' in p.lower() or 'short sentences' in p.lower()


def test_lesson_prompt_difficulty_hard(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "T", "slides": [{"type": "title", "title": "T", "subtitle": "T"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Physics", "Learn mechanics", None, difficulty='Hard')
    p = captured_prompt['prompt']

    assert 'AUDIENCE — Hard' in p
    assert 'age 14–15' in p
    assert 'full subject vocabulary' in p.lower() or 'do not filter' in p.lower()


def test_lesson_prompt_difficulty_normal_default(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module
    captured_prompt = {}

    def mock_call_ollama(prompt, model=None):
        captured_prompt['prompt'] = prompt
        return '{"module_title": "T", "slides": [{"type": "title", "title": "T", "subtitle": "T"}]}'

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    generate_lesson("Physics", "Learn mechanics", None)
    p = captured_prompt['prompt']

    assert 'AUDIENCE — Normal' in p
    assert 'age 12–13' in p


def test_narration_script_has_intro_and_outro(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    slides = [
        {'type': 'title', 'title': 'Intro', 'subtitle': 'Getting Started'},
        {'type': 'content', 'heading': 'Overview', 'bullets': ['Point A', 'Point B']},
    ]
    script = generate_narration_script('Test Module', slides, 'Alice')
    assert isinstance(script, list)
    assert len(script) >= 3
    assert script[0]['slide_index'] == -1
    assert script[-1]['slide_index'] == len(slides)


def test_narration_script_intro_contains_username(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    slides = [
        {'type': 'title', 'title': 'Intro', 'subtitle': 'Getting Started'},
    ]
    script = generate_narration_script('Test Module', slides, 'Bob')
    intro = script[0]['text']
    assert 'Bob' in intro


def test_narration_script_falls_back_on_ai_error(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module

    def mock_call_ollama_raises(prompt, model=None):
        from src.services.exceptions import AIServiceError
        raise AIServiceError('Simulated AI failure')

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama_raises)

    slides = [
        {'type': 'title', 'title': 'Intro', 'subtitle': 'Getting Started'},
    ]
    script = generate_narration_script('Test Module', slides, 'Alice')
    assert isinstance(script, list)
    assert script[0]['slide_index'] == -1
    assert script[-1]['slide_index'] == len(slides)
    assert 'Alice' in script[0]['text']


def test_narration_script_last_module_congratulatory(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    import src.services.lesson_generator as lg_module

    def mock_call_ollama(prompt, model=None):
        return json.dumps([
            {'slide_index': -1, 'text': 'Hello Alice! Welcome to the final module.'},
            {'slide_index': 0, 'text': 'Let us begin.'},
            {'slide_index': 1, 'text': 'Congratulations on completing everything! You did great.'},
        ])

    monkeypatch.setattr(lg_module, 'call_ollama', mock_call_ollama)

    slides = [
        {'type': 'title', 'title': 'Final Module', 'subtitle': 'The End'},
    ]
    script = generate_narration_script('Final Module', slides, 'Alice', is_last_module=True)
    assert script[-1]['slide_index'] == len(slides)
    assert 'congratulations' in script[-1]['text'].lower() or 'completing' in script[-1]['text'].lower()
