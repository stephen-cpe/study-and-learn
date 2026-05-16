"""
AI client wrapper for interacting with Ollama.

Backend selection via the ``AI_BACKEND`` environment variable:
* ``local`` (default) — calls a local Ollama server
* ``cloud``         — calls the Ollama Cloud OpenAI-compatible endpoint

``AI_MOCK=true`` short-circuits both backends and returns deterministic
stub responses (used in CI/tests).
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# AI_MOCK is highest priority — short-circuit before backend selection
if os.environ.get('AI_MOCK', '').lower() == 'true':
    def call_ollama(prompt: str, model: str = None) -> str:  # noqa: D401
        """Return a deterministic mock response."""
        logger.info("Using MOCK response")
        return f"Mock response for prompt: {prompt[:50]}..."
else:
    _backend = os.environ.get('AI_BACKEND', 'local').lower()

    if _backend == 'cloud':
        from .ai_client_cloud import call_ollama  # noqa: F401
    else:
        # ── Local Ollama implementation ──────────────────────────────────

        def call_ollama(prompt: str, model: str = None) -> str:
            """Call local Ollama API to generate a response from a prompt."""
            if model is None:
                model = os.environ.get('OLLAMA_MODEL', 'qwen3:0.6b')

            base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
            url = f"{base_url}/api/generate"
            timeout = int(os.environ.get('OLLAMA_TIMEOUT', '180'))

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
