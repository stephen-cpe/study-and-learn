import io
import tempfile
import pytest
from unittest.mock import patch
from cachelib import FileSystemCache
from src import create_app

@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = temp_dir
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['SESSION_TYPE'] = 'cachelib'
        app.config['SESSION_CACHELIB'] = FileSystemCache(cache_dir=temp_dir, threshold=500, mode=0o700)
        app.config['SESSION_PERMANENT'] = False
        from flask_session import Session
        Session(app)
        with app.test_client() as client:
            with app.app_context():
                yield client

@patch('src.services.rag_retriever.build_rag_context')
@patch('src.services.summarizer.call_ollama')
@patch('src.services.relevance_checker.call_ollama')
@patch('src.services.curriculum_generator.call_ollama')
def test_full_workflow(mock_curriculum, mock_relevance, mock_summarizer, mock_rag, client):
    mock_rag.return_value = "RAG context for testing."
    mock_summarizer.return_value = "Main topics: ML, algorithms. Difficulty: intermediate."
    mock_relevance.return_value = '{"relevance_label": "strong", "explanation": "Good match", "missing_material": "None"}'
    mock_curriculum.return_value = '{"modules": [{"title": "Intro to ML", "estimated_effort": "2 hours"}]}'

    data = {
        'learning_goal': 'Learn ML',
        'files': [(io.BytesIO(b'Sample ML text'), 'test.txt')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)

    assert response.status_code == 200
    assert b'Processed 1 file(s) successfully!' in response.data
    assert b'Intro to ML' in response.data
    assert b'Strong' in response.data
    assert b'Start Over' in response.data

@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_generate_lessons_flow(mock_quiz_ollama, mock_lesson_ollama, client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro to ML", "slides": [{"type": "title", "title": "Intro", "subtitle": "ML Basics"}, {"type": "content", "heading": "Overview", "bullets": ["Point 1", "Point 2"], "notes": ""}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "What is ML?", "options": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "ML is AI"}]}'

    with client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn ML'
        sess['study_path'] = {
            'modules': [
                {'title': 'Intro to ML', 'estimated_effort': '2 hours'}
            ]
        }
        sess['extracted_texts'] = ['Sample text']

    response = client.post('/generate-lessons', follow_redirects=True)
    assert response.status_code == 200
    assert b'Generated' in response.data or b'successfully' in response.data

@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_lesson_deck_route(mock_quiz_ollama, mock_lesson_ollama, client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "true_false", "prompt": "Test?", "answer": true, "explanation": "Yes"}]}'

    with client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']
        sess['lessons'] = [{
            'index': 0, 'module_title': 'M1', 'estimated_effort': '1h',
            'lesson': {'module_title': 'M1', 'slides': [{'type': 'title', 'title': 'M1', 'subtitle': ''}]},
            'quiz': {'questions': [{'id': 'q1', 'type': 'true_false', 'prompt': 'T?', 'answer': True, 'explanation': 'E'}]},
            'checkpoints': {},
            'completed': False, 'score': None, 'passed': False
        }]

    response = client.get('/lessons/0')
    assert response.status_code == 200
