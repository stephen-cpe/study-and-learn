"""Unit tests for the token/context budget helpers in ``rag_budget``.

These tests pin the contract that the RAG retrieval depth and character
budget scale with ``OLLAMA_NUM_CTX``, and that coverage estimation is
defensive (returns safe defaults on error rather than crashing upload).
"""
from src.services import rag_budget


def test_budget_scales_linearly_with_num_ctx(monkeypatch):
    """A 256K context should produce ~2x the char budget of 128K."""
    monkeypatch.setenv('OLLAMA_NUM_CTX', '128000')
    b128 = rag_budget.get_context_budget_chars(max_chars_cap=10**9)
    monkeypatch.setenv('OLLAMA_NUM_CTX', '256000')
    b256 = rag_budget.get_context_budget_chars(max_chars_cap=10**9)
    assert b256 > b128
    # roughly double (256/128 == 2); allow float slop
    assert abs(b256 / b128 - 2.0) < 0.05


def test_budget_respects_max_chars_cap(monkeypatch):
    """The explicit max_chars cap must clamp the derived budget."""
    monkeypatch.setenv('OLLAMA_NUM_CTX', '1000000')
    capped = rag_budget.get_context_budget_chars(max_chars_cap=5000)
    assert capped == 5000


def test_top_k_for_budget_raises_small_default(monkeypatch):
    """With a huge context window the budget-derived top_k exceeds the default."""
    monkeypatch.setenv('OLLAMA_NUM_CTX', '1000000')
    monkeypatch.delenv('RAG_TOP_K', raising=False)
    top_k = rag_budget.get_top_k_for_budget()
    assert top_k > 20


def test_top_k_for_budget_respects_explicit_override(monkeypatch):
    """An explicit RAG_TOP_K larger than the budget-derived value wins."""
    monkeypatch.setenv('OLLAMA_NUM_CTX', '128000')
    monkeypatch.setenv('RAG_TOP_K', '999')
    assert rag_budget.get_top_k_for_budget() == 999


def test_estimate_coverage_ratio_clamped():
    assert rag_budget.estimate_coverage_ratio(50, 100) == 0.5
    assert rag_budget.estimate_coverage_ratio(0, 100) == 0.0
    # retrieved can exceed total due to overlap; clamp to 1.0
    assert rag_budget.estimate_coverage_ratio(500, 100) == 1.0
    # no document -> no warning
    assert rag_budget.estimate_coverage_ratio(0, 0) == 1.0


def test_estimate_total_chars_empty_input():
    assert rag_budget.estimate_total_chars([]) == 0
    assert rag_budget.estimate_total_chars(None) == 0
