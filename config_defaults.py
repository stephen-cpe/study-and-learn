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
OLLAMA_MODEL_CLOUD_DEFAULT = "gemma4:31b-cloud"
OLLAMA_BASE_URL_DEFAULT = "http://localhost:11434"
OLLAMA_CLOUD_BASE_URL_DEFAULT = "https://ollama.com"
OLLAMA_TIMEOUT_DEFAULT = 300
OLLAMA_NUM_CTX_DEFAULT = 131072
RAG_TOP_K_DEFAULT = 20
EMBEDDING_MODEL_DEFAULT = "qwen3-embedding:0.6b"
# OCR and vision are consolidated onto a single natively multimodal model.
# ``glm-ocr`` (local-only) has been removed — all image OCR, table
# extraction, and figure description now use VISION_MODEL_DEFAULT via the
# active AI backend (Ollama Cloud ``glm-5.3-flash:cloud`` by default).
# ``OCR_MODEL_DEFAULT`` is kept as a deprecated alias so old imports keep
# working; new code should use ``VISION_MODEL_DEFAULT`` directly.
VISION_MODEL_DEFAULT = "glm-5.3-flash:cloud"
OCR_MODEL_DEFAULT = VISION_MODEL_DEFAULT

# ── Smart OCR gating defaults ─────────────────────────────────────────────
# Vision OCR is enabled by default (OCR_FULL=true) but only *runs* on PDFs
# that actually need it: scanned/image-heavy files with little extractable
# text. Text-layer PDFs skip rendering + LLM calls entirely.
# A PDF needs vision OCR when total text-layer chars fall below
# PDF_NEEDS_OCR_MIN_TOTAL_CHARS, or average chars/page fall below
# PDF_NEEDS_OCR_MIN_CHARS_PER_PAGE, or embedded images outnumber pages.
PDF_NEEDS_OCR_MIN_TOTAL_CHARS_DEFAULT = 1000
PDF_NEEDS_OCR_MIN_CHARS_PER_PAGE_DEFAULT = 300

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

# ── External web-suggestion defaults (opt-in, fail-closed) ─────────────
# Web search fires ONLY when internal doc topics are exhausted AND the
# topic classifies as public. Proprietary docs never touch the web.
# Reuses OLLAMA_CLOUD_API_KEY/BASE_URL (no new secret).
WEB_SEARCH_ENABLED_DEFAULT = False     # ``WEB_SEARCH_ENABLED`` env toggle
WEB_SEARCH_MAX_RESULTS_DEFAULT = 5
WEB_SEARCH_TIMEOUT_DEFAULT = 30
WEB_SEARCH_SYNTH_MODEL_DEFAULT = "gpt-oss:20b-cloud"