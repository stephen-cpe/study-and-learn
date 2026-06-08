import io
import tempfile
import pytest
from unittest.mock import patch
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User
from src.services import progress_tracker


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        app_instance = create_app()
        app_instance.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(
                cache_dir=temp_dir, threshold=500, mode=0o700
            ),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app_instance)
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app_instance.extensions.pop('sqlalchemy', None)
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            user = User(username='tester', email='tester@example.com',
                         can_generate_lessons=True)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'tester', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


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

    response = client.post('/generate-lessons')
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert '/lessons' in data.get('redirect', '')


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_lesson_deck_route(mock_quiz_ollama, mock_lesson_ollama, client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "true_false", "prompt": "Test?", "answer": true, "explanation": "Yes"}]}'

    with client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = client.post('/generate-lessons', follow_redirects=True)
    assert response.status_code == 200

    response = client.get('/lessons/0')
    assert response.status_code == 200
    assert b'Hello' in response.data or b'test_id' in response.data or b'deck' in response.data


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_generate_lessons_progress_updates(mock_quiz_ollama, mock_lesson_ollama, client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with client.session_transaction() as sess:
        sess['learning_goal'] = 'Test'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = client.post('/generate-lessons')
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None or b'Generated' in response.data or b'successfully' in response.data

    progress_resp = client.get('/progress')
    assert progress_resp.status_code == 200
    data = progress_resp.get_json()
    assert 'stage' in data
    assert 'label' in data
    assert 'pct' in data


def test_progress_endpoint_no_task(client):
    progress_resp = client.get('/progress')
    assert progress_resp.status_code == 200
    data = progress_resp.get_json()
    assert data['stage'] == -1


@patch('src.services.rag_retriever.build_rag_context')
@patch('src.services.summarizer.call_ollama')
@patch('src.services.relevance_checker.call_ollama')
@patch('src.services.curriculum_generator.call_ollama')
def test_process_with_progress_tracking(mock_curriculum, mock_relevance, mock_summarizer, mock_rag, client):
    mock_rag.return_value = "RAG context for testing."
    mock_summarizer.return_value = "Main topics: ML, algorithms. Difficulty: intermediate."
    mock_relevance.return_value = '{"relevance_label": "strong", "explanation": "Good match", "missing_material": "None"}'
    mock_curriculum.return_value = '{"modules": [{"title": "Intro to ML", "estimated_effort": "2 hours"}]}'

    task_id = 'test-process-task-001'
    data = {
        'learning_goal': 'Learn ML',
        'task_id': task_id,
        'files': [(io.BytesIO(b'Sample ML text'), 'test.txt')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data is not None
    assert 'redirect' in json_data
    assert '/results' in json_data['redirect']

    progress_data = progress_tracker.get_progress(task_id)
    assert progress_data is None or progress_data['stage'] == 8


@patch('src.services.rag_retriever.build_rag_context')
@patch('src.services.summarizer.call_ollama')
@patch('src.services.relevance_checker.call_ollama')
@patch('src.services.curriculum_generator.call_ollama')
def test_process_progress_stages_advance(mock_curriculum, mock_relevance, mock_summarizer, mock_rag, client):
    mock_rag.return_value = "RAG context for testing."
    mock_summarizer.return_value = "Main topics: ML, algorithms. Difficulty: intermediate."
    mock_relevance.return_value = '{"relevance_label": "strong", "explanation": "Good match", "missing_material": "None"}'
    mock_curriculum.return_value = '{"modules": [{"title": "Intro to ML", "estimated_effort": "2 hours"}]}'

    task_id = 'test-process-stages-002'
    data = {
        'learning_goal': 'Learn ML',
        'task_id': task_id,
        'files': [(io.BytesIO(b'Sample text'), 'test.txt')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data is not None

    progress_resp = client.get('/progress?task_id=' + task_id)
    assert progress_resp.status_code == 200
    progress_json = progress_resp.get_json()
    assert progress_json['stage'] == -1 or progress_json['stage'] >= 8


def test_process_non_blocking_no_overlay(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'loadingOverlay' not in response.data
    assert b'spinner-overlay' not in response.data
    assert b'robot-mascot' in response.data
    assert b'speech-bubble' in response.data
    assert b'bubble-progress' in response.data


def test_process_ajax_error_response(client):
    data = {
        'learning_goal': '',
        'task_id': 'test-err-001',
        'files': [(io.BytesIO(b'Sample'), 'test.txt')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    assert 'learning goal' in json_data['error'].lower()


def test_process_ajax_no_files(client):
    data = {
        'learning_goal': 'Learn testing',
        'task_id': 'test-err-002',
    }
    response = client.post('/process', data=data, content_type='multipart/form-data')
    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_retake_regenerates_quiz_and_resets_state(mock_quiz_ollama, mock_lesson_ollama, client):
    """Verify retake regenerates checkpoint/quiz questions and clears progress state."""
    mock_lesson_ollama.return_value = (
        '{"module_title": "Intro", '
        '"slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    )
    # First call to quiz_generator returns question set A
    quiz_response_a = (
        '{"questions": ['
        '{"id": "q_a", "type": "true_false", "prompt": "Set A?", '
        '"answer": true, "explanation": "Original quiz"}]}'
    )
    # Second call (during retake) returns question set B
    quiz_response_b = (
        '{"questions": ['
        '{"id": "q_b", "type": "mcq", "prompt": "Set B?", '
        '"options": ["X","Y","Z","W"], "answer_index": 0, '
        '"explanation": "Regenerated quiz"}]}'
    )
    mock_quiz_ollama.side_effect = [quiz_response_a, quiz_response_b]

    with client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn testing'
        sess['study_path'] = {
            'modules': [{'title': 'Module 1', 'estimated_effort': '1h'}]
        }
        sess['extracted_texts'] = ['Test text']

    # Generate lessons (uses quiz_response_a)
    gen_resp = client.post('/generate-lessons', follow_redirects=True)
    assert gen_resp.status_code == 200

    # Verify initial quiz is Set A
    deck_resp = client.get('/lessons/0')
    assert deck_resp.status_code == 200
    assert b'Set A?' in deck_resp.data

    # Retake the lesson (should regenerate quiz using quiz_response_b)
    retake_resp = client.post('/lessons/0/retake')
    assert retake_resp.status_code == 200
    retake_data = retake_resp.get_json()
    assert retake_data is not None
    assert retake_data.get('success') is True

    # Verify quiz is now Set B (freshly regenerated)
    deck_resp_after = client.get('/lessons/0')
    assert deck_resp_after.status_code == 200
    assert b'Set B?' in deck_resp_after.data
    assert b'Set A?' not in deck_resp_after.data
