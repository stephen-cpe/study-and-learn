"""
Unit tests for the AI client service.
"""
import os
import pytest
from src.services.ai_client import call_ollama


def test_call_ollama_with_mock(monkeypatch):
    """Test that AI_MOCK=true returns a mock response."""
    monkeypatch.setenv('AI_MOCK', 'true')
    response = call_ollama("test prompt")
    assert isinstance(response, str)
    assert response != ''
    assert "Mock response for prompt" in response


def test_call_ollama_without_mock(monkeypatch):
    """Test that without AI_MOCK we call the local backend."""
    monkeypatch.delenv('AI_MOCK', raising=False)
    monkeypatch.delenv('AI_BACKEND', raising=False)

    import requests

    class MockResponse:
        def json(self):
            return {"response": "This is a mocked local Ollama response"}

        def raise_for_status(self):
            pass

    def mock_post(url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(requests, 'post', mock_post)

    from src.services.ai_client import call_ollama
    response = call_ollama("test prompt")
    assert "This is a mocked local Ollama response" in response
