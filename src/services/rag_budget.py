"""
Token/context budgeting for the RAG pipeline.

A recurring class of defect in this app is "the AI only skimmed a few
chunks of the document".  The root cause is twofold:

1.  Retrieval is relevance-filtered, so arbitrary chunks are dropped before
    the LLM ever sees them (the model never "reads" most of the document).
2.  The retrieval depth is not tied to the LLM's context window, so callers
    hard-code small ``top_k`` values that silently cap coverage regardless of
    how much context the model can actually hold.

This module provides a single place to reason about the context window so
callers can request (and get) a context-sized budget instead of guessing.

Budgeting model
---------------
``OLLAMA_NUM_CTX`` declares the model's *total* context window (128 K by
default).  We reserve a slice of that for the system prompt plus the model's
generated output, and allocate the remainder to retrieved context::

    reserved   = num_ctx * RAG_RESERVED_TOKEN_FRACTION   (default 20 %)
    budget     = num_ctx - reserved                       (tokens)
    max_chars  = budget * AVG_CHARS_PER_TOKEN             (≈ 4 chars / token)

That ``max_chars`` value is then the *character* cap used to stop adding
retrieved chunks to the context, and it scales linearly with
``OLLAMA_NUM_CTX`` — so selecting a 256 K or 1 M context model automatically
quadruples the retrieval budget without any code change.

All functions are pure (no I/O, no DB, no LLM calls) so they can be unit
tested and reused by every stage of the pipeline.
"""
from __future__ import annotations

import logging
import os

from config_defaults import (
    OLLAMA_NUM_CTX_DEFAULT,
    RAG_MAX_CONTEXT_CHARS_DEFAULT,
    RAG_TOP_K_DEFAULT,
    SUMMARY_MAP_ENABLED_DEFAULT,
    SUMMARY_MAP_MAX_SECTION_CHARS_DEFAULT,
    SUMMARY_MAP_MAX_SECTIONS_DEFAULT,
    env_int,
)

logger = logging.getLogger(__name__)

# Rough English-prose ratio used to translate between tokens and characters.
# 4 chars/token is the standard rule-of-thumb for English text; we use it to
# convert the token budget into a character budget for our chunker (which
# measures length in characters, not tokens).
AVG_CHARS_PER_TOKEN = 4

# Fraction of the total context window reserved for the prompt template and
# the model's generated output.  The retrieved context should never fill the
# entire window — the model needs room to think and to answer.
RESERVED_TOKEN_FRACTION = 0.20


def get_num_ctx() -> int:
    """Return the configured Ollama context window in tokens."""
    return env_int('OLLAMA_NUM_CTX', OLLAMA_NUM_CTX_DEFAULT)


def _budget_tokens(num_ctx: int | None = None) -> float:
    """Return the token budget available for retrieved context."""
    ctx = num_ctx if num_ctx is not None else get_num_ctx()
    return max(0.0, ctx * (1.0 - RESERVED_TOKEN_FRACTION))


def _budget_chars(num_ctx: int | None = None) -> int:
    """Return the character budget available for retrieved context."""
    return int(_budget_tokens(num_ctx) * AVG_CHARS_PER_TOKEN)


def get_context_budget_chars(
    fraction: float = 1.0,
    *,
    max_chars_cap: int | None = None,
    num_ctx: int | None = None,
) -> int:
    """Return the character budget for retrieved context.

    Args:
        fraction: Fraction of the *available* context budget to use.  ``1.0``
            means "use the budget that remains after reserving space for the
            prompt and the model's output".  Smaller fractions are useful for
            stages that need additional headroom (e.g. a summary prompt that
            already contains a large block of user-supplied text).
        max_chars_cap: Hard ceiling on the returned value.  When ``None`` the
            ceiling is read from ``RAG_MAX_CONTEXT_CHARS`` at call time (with
            a sensible derived default based on ``OLLAMA_NUM_CTX``).
        num_ctx: Override for the context window (used by tests).
    """
    budget = _budget_chars(num_ctx) * max(0.0, min(fraction, 1.0))
    if max_chars_cap is None:
        max_chars_cap = env_int(
            'RAG_MAX_CONTEXT_CHARS', RAG_MAX_CONTEXT_CHARS_DEFAULT
        )
    return int(min(budget, max_chars_cap))


def get_top_k_for_budget(
    *,
    per_collection_top_k: int | None = None,
    default_top_k: int = RAG_TOP_K_DEFAULT,
    avg_chunk_chars: int = 1000,
) -> int:
    """Return a sensible retrieval ``top_k`` that matches the context budget.

    The result is the *larger* of the configured default and the number of
    average-sized chunks that fit in the available context budget.  This means
    a small default (20) is automatically raised when the model has a large
    context window, and never lowered when the admin has explicitly chosen a
    larger value.  The budget is measured **without** the ``RAG_MAX_CONTEXT_CHARS``
    cap — that cap limits characters, not the chunk count we attempt to fetch.
    """
    if per_collection_top_k is None:
        per_collection_top_k = env_int('RAG_TOP_K', default_top_k)
    budget_chars = get_context_budget_chars(max_chars_cap=2**31 - 1)
    budget_top_k = max(1, budget_chars // max(1, avg_chunk_chars))
    return max(per_collection_top_k, int(budget_top_k))


# ── Map-reduce (full-coverage) summary controls ──────────────────────────


def map_reduce_enabled() -> bool:
    """Return True when the full-coverage map step should run."""
    return os.environ.get('RAG_SUMMARY_MAP', '').strip().lower() in (
        '1', 'true', 'yes', 'on',
    ) or (SUMMARY_MAP_ENABLED_DEFAULT and not os.environ.get('RAG_SUMMARY_MAP'))


def map_max_section_chars() -> int:
    """Return the maximum size (chars) of one map-step section."""
    return env_int('RAG_MAP_SECTION_CHARS', SUMMARY_MAP_MAX_SECTION_CHARS_DEFAULT)


def map_max_sections() -> int:
    """Return the maximum number of map-step sections to process."""
    return env_int('RAG_MAP_MAX_SECTIONS', SUMMARY_MAP_MAX_SECTIONS_DEFAULT)


# ── Coverage estimation ─────────────────────────────────────────────────


def estimate_total_chars(file_hashes: list[str]) -> int:
    """Return the total extracted-text character count across the files.

    Reads ``ContentRegistry`` for each ``file_hash`` and sums
    ``len(extracted_text)``.  Missing entries contribute 0.  Any error
    (missing table, DB unavailable) logs a warning and returns 0 so the
    caller degrades gracefully rather than crashing the upload.
    """
    if not file_hashes:
        return 0
    total = 0
    try:
        from src.models import ContentRegistry
        for h in file_hashes:
            if not h:
                continue
            entry = ContentRegistry.query.filter_by(file_hash=h).first()
            if entry and entry.extracted_text:
                total += len(entry.extracted_text)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("estimate_total_chars failed: %s", e)
    return total


def estimate_coverage_ratio(
    retrieved_chars: int,
    total_chars: int,
) -> float:
    """Return `retrieved / total`, clamped to ``[0.0, 1.0]``.

    Returns ``1.0`` when there is nothing to measure (so the UI does not
    flag a "low coverage" warning on an empty upload).
    """
    if total_chars <= 0:
        return 1.0
    return max(0.0, min(1.0, retrieved_chars / float(total_chars)))
