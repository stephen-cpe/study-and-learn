import io
import tempfile
import pytest
from unittest.mock import patch
from app import create_app

@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = temp_dir
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret'
        with app.test_client() as client:
            with app.app_context():
                yield client

@patch('app.services.rag_retriever.build_rag_context')
@patch('app.services.summarizer.call_ollama')
@patch('app.services.relevance_checker.call_ollama')
@patch('app.services.curriculum_generator.call_ollama')
def test_full_workflow(mock_curriculum, mock_relevance, mock_summarizer, mock_rag, client):
    # 1. Return valid JSON strings matching service parsers
    mock_rag.return_value = "RAG context for testing."
    mock_summarizer.return_value = "Main topics: ML, algorithms. Difficulty: intermediate."
    mock_relevance.return_value = '{"relevance_label": "strong", "explanation": "Good match", "missing_material": "None"}'
    mock_curriculum.return_value = '{"modules": [{"title": "Intro to ML", "estimated_effort": "2 hours"}]}'

    # 2. Set learning goal
    client.post('/goal', data={'learning_goal': 'Learn ML'}, follow_redirects=True)

    # 3. Upload file using correct multi-file syntax
    data = {'files': [(io.BytesIO(b'Sample ML text'), 'test.txt')]}
    response = client.post('/upload', data=data, content_type='multipart/form-data', follow_redirects=True)

    # 4. Verify results page contains mocked data
    assert response.status_code == 200
    assert b'Processed 1 file(s) successfully!' in response.data
    assert b'Intro to ML' in response.data
    assert b'Strong' in response.data
    assert b'Start Over' in response.data