import io
import tempfile
import pytest
from app import create_app

@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = temp_dir
        app.config['WTF_CSRF_ENABLED'] = False
        with app.test_client() as client:
            with app.app_context():
                yield client

def test_index(client):
    response = client.get('/')
    assert response.status_code == 200

def test_goal_empty_rejected(client):
    response = client.post('/goal', data={'learning_goal': ''}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Please enter a learning goal' in response.data

def test_goal_valid_accepted(client):
    response = client.post('/goal', data={'learning_goal': 'Learn Python'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Learning goal saved successfully!' in response.data

def test_upload_valid_file(monkeypatch, client):
    # 1. Mock AI calls to avoid needing Ollama in CI
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    # 2. Set goal first (required by route)
    client.post('/goal', data={'learning_goal': 'Learn testing'}, follow_redirects=True)
    # 3. Correct Flask test client syntax for multi-file list
    data = {'files': [(io.BytesIO(b'Test content'), 'test.txt')]}
    response = client.post('/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    # 4. Accept either flash wording
    assert b'Processed' in response.data and b'successfully' in response.data

def test_upload_invalid_extension(client):
    # 1. Set goal first
    client.post('/goal', data={'learning_goal': 'Learn testing'}, follow_redirects=True)
    # 2. Upload invalid file
    data = {'files': [(io.BytesIO(b'Invalid content'), 'test.exe')]}
    response = client.post('/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    # 3. Check rejection message
    assert b'Allowed file types' in response.data or b'No valid files' in response.data