"""
Call-time configuration defaults and env helpers for Study-and-Learn.

This module is the single source of truth for default values used by
services that read environment variables at CALL time (ai_client,
ai_client_cloud, rag_retriever, vector_store, vision_parser). It
deliberately contains NO import-time environment reads — only literal
constants and pure functions — so importing it early (e.g. at test
collection time, before fixtures populate the environment) is always
safe. This matters because ``config.Config`` freezes the environment at
import time; keeping these defaults separate preserves that class's
"import lazily inside create_app()" contract.

``config.py`` imports these same constants to build its ``Config``
attributes, so each default is defined exactly once across the codebase.
"""
import os


def env_default(name: str, fallback: str) -> str:
    """Read string env var *name* at CALL time, or *fallback* if unset/empty."""
    value = os.environ.get(name)
    return value if value else fallback


def env_int(name: str, fallback: int) -> int:
    """Read int env var *name* at CALL time, or *fallback* if unset/invalid."""
    try:
        return int(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return fallback


def env_float(name: str, fallback: float) -> float:
    """Read float env var *name* at CALL time, or *fallback* if unset/invalid."""
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return fallback


# ── Named call-time defaults ────────────────────────────────────────────
# The local and cloud chat-model defaults are intentionally different: a
# small CPU model for local dev, a cloud-served model when OLLAMA_MODEL
# is unset in cloud mode.
OLLAMA_MODEL_LOCAL_DEFAULT = "qwen3:0.6b"
OLLAMA_MODEL_CLOUD_DEFAULT = "gemma4:cloud"
OLLAMA_BASE_URL_DEFAULT = "http://localhost:11434"
OLLAMA_CLOUD_BASE_URL_DEFAULT = "https://ollama.com"
OLLAMA_TIMEOUT_DEFAULT = 300
OLLAMA_NUM_CTX_DEFAULT = 131072
RAG_TOP_K_DEFAULT = 20
EMBEDDING_MODEL_DEFAULT = "qwen3-embedding:0.6b"
OCR_MODEL_DEFAULT = "glm-ocr"
VISION_MODEL_DEFAULT = "glm-5.3-flash:cloud"

# ── RAG retrieval / coverage budget defaults ─────────────────────────────
# These control how much of the uploaded document actually reaches the LLM.
# They are read at CALL time so tests can monkeypatch env vars and so the
# defaults scale automatically with OLLAMA_NUM_CTX (see rag_budget.py).
RAG_PER_COLLECTION_TOP_K_DEFAULT = 12
# Hard ceiling on retrieved-context chars.  Derived from OLLAMA_NUM_CTX when
# unset (see rag_budget.get_context_budget_chars).  Set RAG_MAX_CONTEXT_CHARS
# explicitly to force a smaller budget regardless of the model's window.
RAG_MAX_CONTEXT_CHARS_DEFAULT = 120000
SUMMARY_MAP_ENABLED_DEFAULT = True       # ``RAG_SUMMARY_MAP`` env toggle
SUMMARY_MAP_MAX_SECTION_CHARS_DEFAULT = 6000
SUMMARY_MAP_MAX_SECTIONS_DEFAULT = 80