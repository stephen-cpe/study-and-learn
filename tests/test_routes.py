"""
Unit tests for the main routes.
"""
import pytest
from app import create_app


@pytest.fixture
def client():
    """Create a test client for the app."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_index(client):
    """Test that the homepage returns a 200 status and expected message."""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Study-and-Learn MVP' in response.data