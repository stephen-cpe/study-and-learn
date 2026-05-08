"""
Unit tests for the main routes.
"""
import io
import os
import tempfile
import pytest
from app import create_app


@pytest.fixture
def client():
    """Create a test client for the app."""
    # Create a temporary upload folder for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = temp_dir
        app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
        
        with app.test_client() as client:
            with app.app_context():
                yield client


def test_index(client):
    """Test that the homepage returns a 200 status and expected message."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Study-and-Learn' in response.data


def test_goal_empty_rejected(client):
    """Test that submitting an empty learning goal is rejected."""
    response = client.post('/goal', data={'learning_goal': ''}, follow_redirects=True)
    assert response.status_code == 200
    # Should show error message
    assert b'Please enter a learning goal' in response.data


def test_goal_valid_accepted(client):
    """Test that submitting a valid learning goal is accepted."""
    response = client.post('/goal', data={'learning_goal': 'Learn Python programming'}, follow_redirects=True)
    assert response.status_code == 200
    # Should show success message
    assert b'Learning goal saved successfully!' in response.data
    # Goal should be in session (we can check if it appears on page)
    assert b'Learn Python programming' in response.data


def test_upload_valid_file(client):
    """Test that uploading a valid file is accepted."""
    # First, set a learning goal (required for processing)
    client.post('/goal', data={'learning_goal': 'Learn about testing'}, follow_redirects=True)
    
    # Create a simple text file for testing
    test_file_content = b'This is a test file.'
    
    # Test uploading a .txt file
    data = {
        'file': (io.BytesIO(test_file_content), 'test.txt')
    }
    response = client.post('/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    # Should show success message (now on results page due to processing)
    assert b'File test.txt processed successfully!' in response.data


def test_upload_invalid_extension(client):
    """Test that uploading a file with invalid extension is rejected."""
    # Create a simple executable file for testing
    test_file_content = b'This is not a valid file type.'
    
    # Test uploading an .exe file
    data = {
        'file': (io.BytesIO(test_file_content), 'test.exe')
    }
    response = client.post('/upload', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    # Should show error message about allowed file types
    assert b'Allowed file types are: txt, md, pdf, docx' in response.data