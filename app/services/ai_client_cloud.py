"""
Ollama Cloud client. Drop-in replacement for ai_client.py.

Usage
-----
In `ai_client.py`, uncomment this import at the bottom of the file:

    from .ai_client_cloud import call_ollama  # noqa: E402

That's all. Every module that imports ``call_ollama`` from ``ai_client``
will now route through this cloud client instead of local Ollama.

Environment variables
---------------------
OLLAMA_CLOUD_API_KEY   (required)  Ollama Cloud API key
OLLAMA_CLOUD_BASE_URL  (optional)  Default: https://ollama.com
OLLAMA_MODEL           (optional)  Default: gemma3:27b-cloud
OLLAMA_TIMEOUT         (optional)  Default: 180 seconds
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)


def call_ollama(prompt: str, model: str = None) -> str:
    """Call Ollama Cloud API (OpenAI-compatible endpoint)."""
    if os.environ.get('AI_MOCK', '').lower() == 'true':
        logger.info("Using MOCK response")
        return f"Mock response for prompt: {prompt[:50]}..."

    if model is None:
        model = os.environ.get('OLLAMA_MODEL', 'gemma3:27b-cloud')

    base_url = os.environ.get('OLLAMA_CLOUD_BASE_URL', 'https://ollama.com')
    url = f"{base_url}/v1/chat/completions"
    api_key = os.environ.get('OLLAMA_CLOUD_API_KEY', '')
    timeout = int(os.environ.get('OLLAMA_TIMEOUT', '180'))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    logger.info(f"Calling Ollama Cloud model='{model}' timeout={timeout}s")
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        response_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        logger.info(f"Ollama Cloud success: received {len(response_text)} chars")
        return response_text
    except requests.exceptions.Timeout:
        logger.error(f"Ollama Cloud TIMEOUT after {timeout}s for model '{model}'")
        raise RuntimeError(f"Model '{model}' timed out after {timeout}s.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"Ollama Cloud HTTP ERROR: {response.status_code} {response.text}")
        raise RuntimeError(f"Ollama Cloud API error {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama Cloud REQUEST ERROR: {str(e)}")
        raise RuntimeError(f"Failed to reach Ollama Cloud at {url}: {str(e)}")
