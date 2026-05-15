"""
Unit tests for the AI client service.
"""
import os
import pytest
from src.services.ai_client import call_ollama


def test_call_ollama_with_mock(monkeypatch):
    """Test that AI_MOCK=true returns a mock response.

    Works regardless of whether ai_client.py uses local or cloud Ollama.
    """
    monkeypatch.setenv('AI_MOCK', 'true')

    response = call_ollama("test prompt")
    assert isinstance(response, str)
    assert response != ''
    if 'cloud' in call_ollama.__module__ or 'cloud' in str(type(call_ollama)):
        assert "Mock response for prompt" in response


def test_call_ollama_without_mock(monkeypatch):
    """Test that without AI_MOCK, we attempt to call Ollama (but we don't want to actually call in test).
    We'll monkeypatch the requests.post to avoid making a real HTTP request.

    This test works regardless of whether ai_client.py uses local or cloud Ollama.
    """
    monkeypatch.delenv('AI_MOCK', raising=False)

    import src.services.ai_client as ai_client_module

    is_cloud = getattr(call_ollama, '__module__', '') == 'src.services.ai_client_cloud'

    if is_cloud:
        monkeypatch.setenv('OLLAMA_CLOUD_BASE_URL', 'https://ollama.com')
        monkeypatch.setenv('OLLAMA_CLOUD_API_KEY', 'test-key')
        monkeypatch.setenv('OLLAMA_MODEL', 'gemma3:12b-cloud')
    else:
        monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        monkeypatch.setenv('OLLAMA_MODEL', 'qwen3:0.6b')

    class MockResponse:
        def json(self):
            if is_cloud:
                return {"choices": [{"message": {"content": "This is a mocked cloud Ollama response"}}]}
            else:
                return {"response": "This is a mocked local Ollama response"}

        def raise_for_status(self):
            pass

    def mock_post(url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(ai_client_module.requests, 'post', mock_post)

    response = call_ollama("test prompt")
    if is_cloud:
        assert response == "This is a mocked cloud Ollama response"
    else:
        assert response == "This is a mocked local Ollama response"