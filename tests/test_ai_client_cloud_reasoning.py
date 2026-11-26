"""Cloud reasoning-effort and truncation handling tests."""
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.services.exceptions import AICloudAPIError


def _response(content="{\"ok\": true}", finish_reason="stop", reasoning=None):
    message = {"content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={
            "choices": [{"message": message, "finish_reason": finish_reason}]
        }),
    )


def _prepare(monkeypatch):
    monkeypatch.delenv("AI_MOCK", raising=False)
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "fake-key")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TEMPERATURE", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)
    monkeypatch.delenv("OLLAMA_CHAT_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("OLLAMA_VISION_REASONING_EFFORT", raising=False)


@patch("src.services.ai_client_cloud.requests.post")
def test_chat_payload_unchanged_when_effort_settings_unset(mock_post, monkeypatch):
    _prepare(monkeypatch)
    mock_post.return_value = _response()
    mock_post.return_value.raise_for_status = MagicMock()

    from src.services.ai_client_cloud import call_ollama

    call_ollama("test prompt")
    payload = mock_post.call_args.kwargs["json"]

    assert payload == {
        "model": "gemma4:31b-cloud",
        "messages": [{"role": "user", "content": "test prompt"}],
        "stream": False,
        "response_format": {"type": "json_object"},
        "temperature": 0.25,
        "max_tokens": 8192,
    }
    assert "reasoning_effort" not in payload


@patch("src.services.ai_client_cloud.requests.post")
def test_reasoning_effort_routes_to_chat_and_vision(mock_post, monkeypatch):
    _prepare(monkeypatch)
    monkeypatch.setenv("OLLAMA_CHAT_REASONING_EFFORT", "low")
    monkeypatch.setenv("OLLAMA_VISION_REASONING_EFFORT", "high")
    mock_post.return_value = _response()
    mock_post.return_value.raise_for_status = MagicMock()

    from src.services.ai_client_cloud import call_ollama

    call_ollama("text prompt")
    chat_payload = mock_post.call_args_list[0].kwargs["json"]
    assert chat_payload["reasoning_effort"] == "low"

    call_ollama("vision prompt", images=["aW1hZ2U="])
    vision_payload = mock_post.call_args_list[1].kwargs["json"]
    assert vision_payload["reasoning_effort"] == "high"


@patch("src.services.ai_client_cloud.requests.post")
def test_empty_content_with_length_raises(mock_post, monkeypatch, caplog):
    _prepare(monkeypatch)
    mock_post.return_value = _response(
        content="", finish_reason="length", reasoning="x" * 500)
    mock_post.return_value.raise_for_status = MagicMock()

    from src.services.ai_client_cloud import call_ollama

    with caplog.at_level(logging.ERROR):
        with pytest.raises(AICloudAPIError, match="exhausted max_tokens=8192"):
            call_ollama("test prompt")

    assert "returned empty content" in caplog.text
    assert "reasoning=500 chars" in caplog.text


@patch("src.services.ai_client_cloud.requests.post")
def test_nonempty_content_with_length_returns_and_warns(mock_post, monkeypatch,
                                                         caplog):
    _prepare(monkeypatch)
    mock_post.return_value = _response(
        content="partial output", finish_reason="length")
    mock_post.return_value.raise_for_status = MagicMock()

    from src.services.ai_client_cloud import call_ollama

    with caplog.at_level(logging.WARNING):
        result = call_ollama("test prompt")

    assert result == "partial output"
    assert "truncated at max_tokens" in caplog.text
