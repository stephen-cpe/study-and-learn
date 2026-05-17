"""
AI client wrapper for interacting with Ollama.

Backend selection via the ``AI_BACKEND`` environment variable:
* ``local`` (default) — calls a local Ollama server
* ``cloud``         — calls the Ollama Cloud OpenAI-compatible endpoint

``AI_MOCK=true`` short-circuits both backends and returns deterministic
stub responses (used in CI/tests).

IMPORTANT: ``AI_MOCK`` and ``AI_BACKEND`` are checked at *call time*, not at
import time, so tests can safely use ``monkeypatch.setenv`` before invoking
``call_ollama``.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _call_ollama_local(prompt: str, model: str = None) -> str:
    """Call local Ollama API to generate a response from a prompt."""
    if model is None:
        model = os.environ.get('OLLAMA_MODEL', 'qwen3:0.6b')

    base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    url = f"{base_url}/api/generate"
    timeout = int(os.environ.get('OLLAMA_TIMEOUT', '300'))

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 4096}
    }

    logger.info(f"Calling Ollama model='{model}' timeout={timeout}s")
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        response_text = result.get('response', '')
        logger.info(f"Ollama success: received {len(response_text)} chars")
        return response_text
    except requests.exceptions.Timeout:
        logger.error(f"Ollama TIMEOUT after {timeout}s for model '{model}'")
        raise RuntimeError(
            f"Model '{model}' timed out after {timeout}s. "
            f"Try pulling it first: ollama pull {model}"
        )
    except requests.exceptions.HTTPError as e:
        logger.error(f"Ollama HTTP ERROR: {response.status_code} {response.text}")
        raise RuntimeError(f"Ollama API error {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama REQUEST ERROR: {str(e)}")
        raise RuntimeError(f"Failed to reach Ollama at {url}: {str(e)}")


def call_ollama(prompt: str, model: str = None) -> str:
    """Return an AI response for *prompt*, checking AI_MOCK at call time.

    * If ``AI_MOCK=true`` → deterministic stub (used in CI/tests).
    * If ``AI_BACKEND=cloud`` → delegates to :func:`ai_client_cloud.call_ollama`.
    * Otherwise → local Ollama via :func:`_call_ollama_local`.
    """
    if os.environ.get('AI_MOCK', '').lower() == 'true':
        logger.info("Using MOCK response")
        return f"Mock response for prompt: {prompt[:50]}..."

    backend = os.environ.get('AI_BACKEND', 'local').lower()
    if backend == 'cloud':
        from .ai_client_cloud import call_ollama as cloud_call
        return cloud_call(prompt, model)

    return _call_ollama_local(prompt, model)
