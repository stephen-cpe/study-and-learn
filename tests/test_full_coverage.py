"""Tests for the full-coverage (map-reduce) RAG pipeline.

Guarantees the property the user cares about: the AI is grounded in the
*entire* uploaded document, not only the handful of chunks that similarity
search happened to surface.
"""
from unittest.mock import MagicMock, patch

from src.services import rag_budget, rag_retriever


def test_full_coverage_context_combines_digest_and_retrieval(monkeypatch):
    """context_text must contain both the full digest and the retrieved chunks."""
    monkeypatch.setenv('RAG_SUMMARY_MAP', 'true')
    monkeypatch.setenv('OLLAMA_NUM_CTX', '128000')

    with patch.object(rag_retriever, '_map_summaries', return_value='DIGEST'), \
         patch.object(rag_retriever, 'build_rag_context_from_hashes_with_sources',
                      return_value={'context_text': 'RETRIEVED', 'sources': []}), \
         patch('src.services.rag_retriever.estimate_total_chars', return_value=1000):
        result = rag_retriever.build_full_coverage_context(
            'learn x', ['hash1'], ['doc.txt']
        )

    assert result['content_digest'] == 'DIGEST'
    assert 'DIGEST' in result['context_text']
    assert 'RETRIEVED' in result['context_text']
    assert result['sources'] == []
    assert result['coverage_ratio'] is not None


def test_full_coverage_disabled_returns_plain_retrieval(monkeypatch):
    """RAG_SUMMARY_MAP=false must skip the map step."""
    monkeypatch.setenv('RAG_SUMMARY_MAP', 'false')
    with patch.object(rag_retriever, '_map_summaries') as mock_map, \
         patch.object(rag_retriever, 'build_rag_context_from_hashes_with_sources',
                      return_value={'context_text': 'RETRIEVED', 'sources': []}):
        result = rag_retriever.build_full_coverage_context('g', ['h'])
    mock_map.assert_not_called()
    assert result['content_digest'] == ''
    assert result['coverage_ratio'] is None


def test_map_summaries_creates_one_entry_per_section(monkeypatch):
    """The map step must summarize every section of every file (full coverage)."""
    monkeypatch.setenv('RAG_SUMMARY_MAP', 'true')
    monkeypatch.setenv('RAG_MAP_SECTION_CHARS', '40')

    file_text = ('alpha paragraph one.\n\n' * 5) + 'tail para.'
    captured = []

    def fake_ollama(prompt, *a, **k):
        captured.append(prompt)
        return 'summary'

    fake_entry = MagicMock()
    fake_entry.extracted_text = file_text

    with patch('src.models.ContentRegistry') as mock_cr, \
         patch('src.services.ai_client.call_ollama', side_effect=fake_ollama):
        mock_cr.query.filter_by.return_value.first.return_value = fake_entry
        digest = rag_retriever._map_summaries(
            ['deadbeef'], ['doc.txt'], 'goal', summary_max_chars=200,
        )

    # more than one LLM call — the document was split into multiple sections
    assert len(captured) >= 2
    assert 'doc.txt' in digest
    assert 'section 1/' in digest


def test_map_summaries_llm_failure_degrades_to_verbatim(monkeypatch):
    """If the LLM fails on a section the raw text is kept (coverage preserved)."""
    monkeypatch.setenv('RAG_SUMMARY_MAP', 'true')
    file_text = 'This is the full source text that must survive.'
    fake_entry = MagicMock()
    fake_entry.extracted_text = file_text

    with patch('src.models.ContentRegistry') as mock_cr, \
         patch('src.services.ai_client.call_ollama',
               side_effect=RuntimeError('LLM down')):
        mock_cr.query.filter_by.return_value.first.return_value = fake_entry
        digest = rag_retriever._map_summaries(
            ['deadbeef'], ['doc.txt'], 'goal', summary_max_chars=60,
        )

    assert 'This is the full source text' in digest


def test_split_into_sections_respects_budget():
    from src.services.rag_retriever import _split_into_sections
    text = 'para one.\n\npara two.\n\n' + ('long ' * 500)
    sections = _split_into_sections(text, max_section_chars=200)
    assert all(len(s) <= 200 for s in sections)
    assert ''.join(sections).replace('\n', '') != ''


def test_lesson_retriever_prepends_digest():
    """The lesson-generation retriever must prepend the digest to context."""
    from src.services.lesson_orchestrator import (
        make_retriever_from_hashes_with_names,
    )

    with patch('src.services.lesson_orchestrator.build_rag_context_from_hashes_with_sources',
               return_value={'context_text': 'CHUNK', 'sources': []}):
        retriever = make_retriever_from_hashes_with_names(
            'goal', ['h'], ['f.txt'], content_digest='THE_DIGEST'
        )
        result = retriever('q')

    assert 'THE_DIGEST' in result['context_text']
    assert 'CHUNK' in result['context_text']
    assert result['context_text'].index('THE_DIGEST') < result['context_text'].index('CHUNK')
