"""
Centralized configuration for Study-and-Learn.

All environment variables are resolved here so the rest of the codebase
doesn't have to know about os.environ lookups. Values are validated up-front
so misconfiguration fails fast at startup, not deep in a request.

Usage in src/__init__.py:
    from config import Config
    app.config.from_object(Config)
"""
import os
import sys

from config_defaults import (
    EMBEDDING_MODEL_DEFAULT,
    OLLAMA_BASE_URL_DEFAULT,
    OLLAMA_CLOUD_BASE_URL_DEFAULT,
    OLLAMA_MODEL_CLOUD_DEFAULT,
    OLLAMA_NUM_CTX_DEFAULT,
    OLLAMA_TIMEOUT_DEFAULT,
    RAG_TOP_K_DEFAULT,
    VISION_MODEL_DEFAULT,
)


def _bool(value: str, default: bool = False) -> bool:
    """Parse a string env var into a bool."""
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(value: str, default: int) -> int:
    """Parse a string env var into an int, falling back on bad input."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Config:
    """Flask config object. Reads from os.environ at class definition time."""

    # ── Flask core ──────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-for-testing-only")
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")

    # ── Database ────────────────────────────────────────────────────────
    # Required: postgresql+psycopg2://user:pass@host:5432/dbname
    # Validated in src/__init__.py because it raises RuntimeError on missing.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Server-side sessions (cachelib-backed filesystem) ───────────────
    # Session directory is hardcoded in src/__init__.py (data/flask_session).
    SESSION_TYPE = "cachelib"
    SESSION_PERMANENT = False

    # ── Ollama Cloud (AI backend) ───────────────────────────────────────
    OLLAMA_CLOUD_API_KEY = os.environ.get("OLLAMA_CLOUD_API_KEY", "")
    OLLAMA_CLOUD_BASE_URL = os.environ.get(
        "OLLAMA_CLOUD_BASE_URL", OLLAMA_CLOUD_BASE_URL_DEFAULT
    )
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL_CLOUD_DEFAULT)
    OLLAMA_TIMEOUT = _int(os.environ.get("OLLAMA_TIMEOUT"), OLLAMA_TIMEOUT_DEFAULT)
    OLLAMA_NUM_CTX = _int(os.environ.get("OLLAMA_NUM_CTX"), OLLAMA_NUM_CTX_DEFAULT)
    # RAG coverage scales with OLLAMA_NUM_CTX: the retrieval character budget
    # is derived from the context window (minus a reserved prompt/output
    # fraction), so a 256K/1M model automatically retrieves more chunks.
    RAG_TOP_K = _int(os.environ.get("RAG_TOP_K"), RAG_TOP_K_DEFAULT)

    # ── Local Ollama (alternative backend) ──────────────────────────────
    OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE_URL_DEFAULT)
    # OCR and vision share one model (glm-5.3-flash:cloud). ``OLLAMA_OCR_MODEL``
    # is no longer read — leftovers in old .env files are ignored.
    OLLAMA_VISION_MODEL = os.environ.get(
        "OLLAMA_VISION_MODEL", VISION_MODEL_DEFAULT
    )
    OLLAMA_EMBEDDING_MODEL = os.environ.get(
        "OLLAMA_EMBEDDING_MODEL", EMBEDDING_MODEL_DEFAULT
    )

    # ── OCR / vision pipeline ───────────────────────────────────────────
    # Vision OCR is ON by default (OCR_FULL=true) but smart-gated per file:
    # text-layer PDFs skip rendering + LLM calls (see vision_parser
    #._pdf_needs_vision_ocr). Set OCR_FULL=false to force text-layer-only
    # extraction everywhere (e.g. offline / zero-cost mode).
    OCR_MAX_IMAGE_DIMENSION = _int(
        os.environ.get("OCR_MAX_IMAGE_DIMENSION"), 2048
    )
    OCR_MAX_FILE_BYTES = _int(
        os.environ.get("OCR_MAX_FILE_BYTES"), 50 * 1024 * 1024
    )
    OCR_TIMEOUT_PER_PAGE = _int(
        os.environ.get("OCR_TIMEOUT_PER_PAGE"), 120
    )
    OCR_FULL = _bool(os.environ.get("OCR_FULL"), True)
    OCR_FIGURE_DESCRIPTION = _bool(
        os.environ.get("OCR_FIGURE_DESCRIPTION"), True
    )

    # ── Poppler (cross-platform PDF rendering) ──────────────────────────
    # Resolved by src.services.vision_parser._get_poppler_path() at call time.
    POPPLER_PATH = os.environ.get("POPPLER_PATH", "").strip() or None

    # ── Vector store / ChromaDB ─────────────────────────────────────────
    # CI=true forces EphemeralClient (in-memory) for test isolation.
    CI = _bool(os.environ.get("CI"))

    # ChromaDB backend selector: "local" (default, PersistentClient) or
    # "cloud" (CloudClient). Read at call time in vector_store.py
    # (mirrors the AI_BACKEND pattern) — do not read this from
    # current_app.config. If "cloud" is requested but credentials are
    # missing/invalid, get_chroma_client() logs and falls back to local.
    CHROMA_DB = os.environ.get("CHROMA_DB", "local").strip().lower() or "local"

    # Chroma Cloud credentials (only used when CHROMA_DB=cloud).
    # CHROMA_CLOUD_CONNECTION_STRING is the Chroma tenant ID.
    # CHROMA_COLLECTION_NAME becomes the Chroma Cloud database name
    # (per-file collections doc_<hash> live inside it).
    CHROMA_CLOUD_API_KEY = os.environ.get("CHROMA_CLOUD_API_KEY", "")
    CHROMA_CLOUD_CONNECTION_STRING = os.environ.get(
        "CHROMA_CLOUD_CONNECTION_STRING", ""
    )
    CHROMA_COLLECTION_NAME = os.environ.get(
        "CHROMA_COLLECTION_NAME", "study-and-learn-chromadb"
    )

    # ── AI client mode ──────────────────────────────────────────────────
    # AI_MOCK=true returns canned responses without hitting any backend.
    AI_MOCK = _bool(os.environ.get("AI_MOCK"))

    # ── Diagnostics ─────────────────────────────────────────────────────
    @classmethod
    def summary(cls) -> str:
        """One-line summary of the active configuration (no secrets)."""
        return (
            f"Config(env={sys.platform!r}, "
            f"db={'set' if cls.SQLALCHEMY_DATABASE_URI else 'MISSING'}, "
            f"ai_key={'set' if cls.OLLAMA_CLOUD_API_KEY else 'MISSING'}, "
            f"model={cls.OLLAMA_MODEL!r}, "
            f"poppler={'override' if cls.POPPLER_PATH else 'auto-detect'}, "
            f"chroma={cls.CHROMA_DB!r}, "
            f"mock={cls.AI_MOCK})"
        )
