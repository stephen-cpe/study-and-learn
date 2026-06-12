import io
import tempfile
import pytest
from unittest.mock import patch
from cachelib import FileSystemCache
from src import create_app

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
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

def test_index(client):
    response = client.get('/')
    assert response.status_code == 200

def test_process_empty_goal_rejected(client):
    data = {
        'learning_goal': '',
        'files': [(io.BytesIO(b'Test content'), 'test.txt')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Please enter a learning goal' in response.data

def test_process_no_files_rejected(client):
    response = client.post('/process', data={'learning_goal': 'Learn testing'},
                           content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'No valid files' in response.data

def test_process_valid(monkeypatch, client):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    monkeypatch.setenv('CI', 'true')

    data = {
        'learning_goal': 'Learn testing',
        'files': [(io.BytesIO(b'Test content'), 'test.txt')]
    }
    with patch("src.services.vision_parser.is_content_registered", return_value=None), \
         patch("src.services.vision_parser.register_content"):
        response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Processed' in response.data and b'successfully' in response.data

def test_process_invalid_extension(client):
    data = {
        'learning_goal': 'Learn testing',
        'files': [(io.BytesIO(b'Invalid content'), 'test.exe')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Allowed file types' in response.data or b'No valid files' in response.data

def test_process_max_files(client):
    files = [(io.BytesIO(f'Content {i}'.encode()), f'test{i}.txt') for i in range(6)]
    data = {'learning_goal': 'Learn testing', 'files': files}
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Maximum' in response.data and b'5' in response.data


def test_cloze_dropdown_grader():
    from src.services.grader import _grade_single_question, _get_correct_answer
    q = {
        'id': 'q1', 'type': 'cloze_dropdown',
        'prompt': 'Water is ___.',
        'options': ['H2O', 'CO2', 'NaCl', 'O2'],
        'answer_index': 0, 'explanation': 'Water is H2O.'
    }
    assert _grade_single_question(q, 0) is True
    assert _grade_single_question(q, 1) is False
    assert _grade_single_question(q, None) is False
    assert _get_correct_answer(q) == 0
