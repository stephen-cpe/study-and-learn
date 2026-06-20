"""
Ollama Cloud client. Called by ai_client.py when AI_BACKEND=cloud.

Integration
-----------
``ai_client.py::call_ollama`` reads the ``AI_BACKEND`` env var at *call time*.
When ``AI_BACKEND=cloud`` (and ``AI_MOCK`` is not set, and ``force_local`` is
False), it lazy-imports this module and delegates::

    from .ai_client_cloud import call_ollama as cloud_call
    return cloud_call(prompt, model)

There is no "uncomment an import" step — backend selection is exclusively
env-var-driven. See ADR-007 (SRS.md §4.4) and AI_AGENT_PROTOCOL.md for the
``AI_BACKEND`` / ``AI_MOCK`` / ``force_local`` rules.

Environment variables
---------------------
OLLAMA_CLOUD_API_KEY   (required)  Ollama Cloud API key
OLLAMA_CLOUD_BASE_URL  (optional)  Default: https://ollama.com
OLLAMA_MODEL           (optional)  Default: gemma3:27b-cloud
OLLAMA_TIMEOUT         (optional)  Default: 300 seconds
"""
import os
import logging
import requests

from src.services.exceptions import (
    AIServiceError, AIModelUnavailableError, AICloudAPIError, AITimeoutError,
)

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
    timeout = int(os.environ.get('OLLAMA_TIMEOUT', '300'))

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
    except requests.exceptions.ConnectTimeout:
        logger.error(f"Ollama Cloud CONNECT TIMEOUT for model '{model}'")
        raise AIModelUnavailableError(
            "Could not connect to Ollama Cloud. Check your internet connection."
        )
    except requests.exceptions.ReadTimeout:
        logger.error(f"Ollama Cloud READ TIMEOUT after {timeout}s for model '{model}'")
        raise AITimeoutError(
            f"Cloud model '{model}' took too long to respond ({timeout}s timeout). "
            f"Try again or use a smaller model."
        )
    except requests.exceptions.HTTPError as e:
        status = response.status_code
        logger.error(f"Ollama Cloud HTTP ERROR: {status} {response.text}")
        if status == 400:
            raise AICloudAPIError(
                f"Cloud API rejected the request for model '{model}'. "
                f"The model may not be available or the request is malformed."
            )
        elif status in (401, 403):
            raise AICloudAPIError(
                "Cloud API authentication failed. Check your OLLAMA_CLOUD_API_KEY."
            )
        elif status == 404:
            raise AICloudAPIError(
                f"Cloud model '{model}' not found. "
                f"Verify the model name includes the '-cloud' suffix."
            )
        elif status >= 500:
            raise AICloudAPIError(
                f"Cloud API server error ({status}). The service may be temporarily "
                f"unavailable. Try again in a moment."
            )
        else:
            raise AICloudAPIError(f"Cloud API error {status}: {response.text}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Ollama Cloud CONNECTION ERROR: {str(e)}")
        raise AIModelUnavailableError(
            "Could not connect to Ollama Cloud. Check your internet connection."
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama Cloud REQUEST ERROR: {str(e)}")
        raise AIModelUnavailableError(f"Failed to reach Ollama Cloud at {url}: {str(e)}")
