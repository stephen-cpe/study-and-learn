"""
Integration tests for the full workflow.
"""
import io
import tempfile
import pytest
from unittest.mock import patch
from app import create_app


@pytest.fixture
def client():
    """Create a test client for the app."""
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = temp_dir
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret-key'
        
        with app.test_client() as client:
            with app.app_context():
                yield client


@patch('app.services.summarizer.call_ollama')
@patch('app.services.relevance_checker.call_ollama')
@patch('app.services.curriculum_generator.call_ollama')
def test_full_workflow(mock_curriculum, mock_relevance, mock_summarizer, client):
    """Test the full workflow: goal setting, file upload, processing, and results page."""
    # Configure mocks to return deterministic responses
    mock_summarizer.return_value = "Main topics: machine learning, algorithms\nDifficulty: intermediate\nPrerequisites: basic programming"
    mock_relevance.return_value = '{"relevance_label": "strong", "explanation": "The document matches the learning goal well.", "missing_material": "None"}'
    mock_curriculum.return_value = '{"modules": [{"title": "Introduction to Machine Learning", "estimated_effort": "2 hours"}, {"title": "Types of Machine Learning Algorithms", "estimated_effort": "3 hours"}]}'
    
    # Step 1: Set the learning goal
    response = client.post('/goal', data={'learning_goal': 'Learn about machine learning'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Study-and-Learn MVP' in response.data
    
    # Step 2: Upload a file
    test_file_content = b'This is a sample text about machine learning algorithms.'
    data = {
        'file': (io.BytesIO(test_file_content), 'test.txt')
    }
    response = client.post('/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    
    # Check results page content
    assert b'Main topics: machine learning, algorithms' in response.data
    assert b'Difficulty: intermediate' in response.data
    assert b'Prerequisites: basic programming' in response.data
    assert b'Strong' in response.data
    assert b'The document matches the learning goal well.' in response.data
    assert b'Introduction to Machine Learning' in response.data
    assert b'2 hours' in response.data
    assert b'Types of Machine Learning Algorithms' in response.data
    assert b'3 hours' in response.data
    assert b'Start Over' in response.data