"""
Unit tests for RAG services: chunker and vector_store.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


def test_chunk_text_basic():
    """Test that chunk_text splits text correctly."""
    from app.services.chunker import chunk_text
    
    text = "This is sentence one. This is sentence two. This is sentence three."
    chunks = chunk_text(text)
    
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert all(isinstance(c, str) for c in chunks)


def test_chunk_text_empty():
    """Test that chunk_text handles empty text."""
    from app.services.chunker import chunk_text
    
    chunks = chunk_text("")
    assert chunks == []
    
    chunks = chunk_text("   ")
    assert chunks == []


def test_chunk_text_preserves_content():
    """Test that chunked text preserves original content."""
    from app.services.chunker import chunk_text
    
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text)
    
    combined = "".join(chunks)
    assert "First paragraph" in combined
    assert "Second paragraph" in combined
    assert "Third paragraph" in combined


def test_vector_store_imports():
    """Test that vector_store module can be imported."""
    from app.services import vector_store
    assert hasattr(vector_store, 'get_chroma_client')
    assert hasattr(vector_store, 'store_chunks')
    assert hasattr(vector_store, 'retrieve_context')


def test_build_rag_context_no_files():
    """Test RAG context builder with no files."""
    from app.services.rag_retriever import build_rag_context
    
    context = build_rag_context("test goal", [])
    assert context == ""


@patch('app.services.rag_retriever.chunk_text')
@patch('app.services.rag_retriever.store_chunks')
@patch('app.services.rag_retriever.retrieve_context')
def test_build_rag_context_single_file(mock_retrieve, mock_store, mock_chunk):
    """Test RAG context builder with single file."""
    from app.services.rag_retriever import build_rag_context
    
    mock_chunk.return_value = ["chunk1", "chunk2"]
    mock_store.return_value = "stored"
    mock_retrieve.return_value = "retrieved context"
    
    context = build_rag_context("test goal", ["file content"])
    
    assert context == "retrieved context"
    mock_chunk.assert_called_once()
    mock_store.assert_called_once()
    mock_retrieve.assert_called_once()