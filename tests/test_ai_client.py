"""
Unit tests for the AI client service.
"""
import os
import pytest
from app.services.ai_client import call_ollama


def test_call_ollama_with_mock(monkeypatch):
    """Test that AI_MOCK=true returns a mock response."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    # Also set OLLAMA_BASE_URL to something, though it shouldn't be used
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    response = call_ollama("test prompt")
    # The mock should return a string
    assert isinstance(response, str)
    # We can check for a known mock response if we define one in the service
    # For now, we just check it's a string and not empty
    assert response != ''


def test_call_ollama_without_mock(monkeypatch):
    """Test that without AI_MOCK, we attempt to call Ollama (but we don't want to actually call in test).
    We'll monkeypatch the requests.post to avoid real calls.
    """
    # Unset AI_MOCK
    monkeypatch.delenv('AI_MOCK', raising=False)
    # Set OLLAMA_BASE_URL
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # We'll mock requests.post to avoid making a real HTTP request
    class MockResponse:
        def json(self):
            return {"response": "This is a mocked Ollama response"}
        
        def raise_for_status(self):
            pass

    def mock_post(*args, **kwargs):
        return MockResponse()

    # We need to patch the requests.post inside the ai_client module
    import app.services.ai_client as ai_client_module
    monkeypatch.setattr(ai_client_module.requests, 'post', mock_post)

    response = call_ollama("test prompt")
    assert response == "This is a mocked Ollama response"