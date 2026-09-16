"""
Ollama web search / fetch client (external suggestions phase).

Separate REST APIs — NOT a model property. Plain
``/v1/chat/completions`` calls have no live browsing (gpt-oss says so
explicitly; nemotron/gemma return stale/illustrative dates). These
``/api/web_search`` + ``/api/web_fetch`` endpoints do:

* ``POST {base}/api/web_search {query, max_results}`` →
  ``{"results": [{title, url, content}]}``
* ``POST {base}/api/web_fetch {url}`` →
  ``{"title":..., "content":...}``

Auth reuses ``OLLAMA_CLOUD_API_KEY``. All functions never raise —
return [] / "" so suggestions degrade to internal-only.
"""
from __future__ import annotations

import logging

import requests

from config_defaults import (
    OLLAMA_CLOUD_BASE_URL_DEFAULT,
    env_default,
    env_int,
)

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return env_default('OLLAMA_CLOUD_BASE_URL', OLLAMA_CLOUD_BASE_URL_DEFAULT)


def _api_key() -> str:
    import os
    return os.environ.get('OLLAMA_CLOUD_API_KEY', '') or ''


def _mock_enabled() -> bool:
    import os
    return os.environ.get('AI_MOCK', '').lower() == 'true'


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web. Returns [{title, url, content}]. Never raises."""
    query = (query or '').strip()
    if not query:
        return []
    if _mock_enabled():
        return []
    if not _api_key():
        return []
    try:
        limit = max(1, min(int(max_results or 5), 10))
    except (TypeError, ValueError):
        limit = 5
    timeout = env_int('WEB_SEARCH_TIMEOUT', 30)
    try:
        resp = requests.post(
            f"{_base_url()}/api/web_search",
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={"query": query[:500], "max_results": limit},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get('results', []) if isinstance(data, dict) else []
        out = []
        for r in results:
            if not isinstance(r, dict):
                continue
            url = str(r.get('url', '') or '').strip()
            if not url.startswith(('http://', 'https://')):
                continue
            out.append({
                'title': str(r.get('title', '') or '').strip()[:200],
                'url': url[:1000],
                'content': str(r.get('content', '') or '').strip()[:4000],
            })
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        logger.warning("web_search failed: %s", str(e))
        return []


def web_fetch(url: str, max_chars: int = 6000) -> str:
    """Fetch one page. Returns text ("" on failure). Never raises."""
    url = (url or '').strip()
    if not url.startswith(('http://', 'https://')):
        return ''
    if _mock_enabled():
        return ''
    if not _api_key():
        return ''
    timeout = env_int('WEB_SEARCH_TIMEOUT', 30)
    try:
        resp = requests.post(
            f"{_base_url()}/api/web_fetch",
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={"url": url[:1000]},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return ''
        text = str(data.get('content', '') or '').strip()
        return text[:max_chars] if len(text) > max_chars else text
    except Exception as e:
        logger.warning("web_fetch failed for %s: %s", url[:80], str(e))
        return ''
