"""
Unit tests for RAG services: chunker and vector_store.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


def test_chunk_text_basic():
    """Test that chunk_text splits text correctly."""
    from src.services.chunker import chunk_text
    
    text = "This is sentence one. This is sentence two. This is sentence three."
    chunks = chunk_text(text)
    
    assert isinstance(chunks, list)
    assert len(chunks) > 0
    assert all(isinstance(c, str) for c in chunks)


def test_chunk_text_empty():
    """Test that chunk_text handles empty text."""
    from src.services.chunker import chunk_text
    
    chunks = chunk_text("")
    assert chunks == []
    
    chunks = chunk_text("   ")
    assert chunks == []


def test_chunk_text_preserves_content():
    """Test that chunked text preserves original content."""
    from src.services.chunker import chunk_text
    
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text)
    
    combined = "".join(chunks)
    assert "First paragraph" in combined
    assert "Second paragraph" in combined
    assert "Third paragraph" in combined


def test_vector_store_imports():
    """Test that vector_store module can be imported."""
    from src.services import vector_store
    assert hasattr(vector_store, 'get_chroma_client')
    assert hasattr(vector_store, 'store_chunks')
    assert hasattr(vector_store, 'retrieve_context')


def test_build_rag_context_no_files():
    """Test RAG context builder with no files."""
    from src.services.rag_retriever import build_rag_context
    
    context = build_rag_context("test goal", [])
    assert context == ""


@patch('src.services.rag_retriever.chunk_text')
@patch('src.services.rag_retriever.store_chunks')
@patch('src.services.rag_retriever.retrieve_context')
def test_build_rag_context_single_file(mock_retrieve, mock_store, mock_chunk):
    """Test RAG context builder with single file."""
    from src.services.rag_retriever import build_rag_context
    
    mock_chunk.return_value = ["chunk1", "chunk2"]
    mock_store.return_value = "stored"
    mock_retrieve.return_value = "retrieved context"
    
    context = build_rag_context("test goal", ["file content"])
    
    assert context == "retrieved context"
    mock_chunk.assert_called_once()
    mock_store.assert_called_once()
    mock_retrieve.assert_called_once()


def test_get_collection_name():
    from src.services.vector_store import get_collection_name
    name = get_collection_name("abc123")
    assert name == "doc_abc123"


@patch('src.services.vector_store.get_chroma_client')
def test_store_chunks_with_metadata(mock_client):
    from src.services.vector_store import store_chunks
    mock_collection = MagicMock()
    mock_client.return_value.get_or_create_collection.return_value = mock_collection

    with patch('langchain_ollama.OllamaEmbeddings') as mock_emb:
        mock_inst = MagicMock()
        mock_inst.embed_documents.return_value = [[0.1] * 384, [0.1] * 384]
        mock_emb.return_value = mock_inst
        result = store_chunks(["c1", "c2"], "test_coll",
                              metadata=[{"source": "a"}, {"source": "b"}])
        assert "Stored" in result
        call_kwargs = mock_collection.add.call_args
        assert "metadatas" in call_kwargs[1] or "metadatas" in call_kwargs.kwargs


@patch('src.services.vector_store.get_chroma_client')
def test_retrieve_with_scores(mock_client):
    from src.services.vector_store import retrieve_with_scores
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        'documents': [["doc1", "doc2"]],
        'distances': [[0.1, 0.3]],
        'metadatas': [[{"k": "v1"}, {"k": "v2"}]]
    }
    mock_client.return_value.get_or_create_collection.return_value = mock_collection

    with patch('langchain_ollama.OllamaEmbeddings') as mock_emb:
        mock_inst = MagicMock()
        mock_inst.embed_query.return_value = [0.1] * 384
        mock_emb.return_value = mock_inst
        results = retrieve_with_scores("query", "test_coll")
        assert len(results) == 2
        for r in results:
            assert 'document' in r
            assert 'score' in r
            assert 'metadata' in r


@patch('src.services.vector_store.get_chroma_client')
def test_retrieve_from_multiple_collections(mock_client):
    from src.services.vector_store import retrieve_from_multiple_collections
    coll1 = MagicMock()
    coll1.query.return_value = {
        'documents': [["from_coll1"]],
        'distances': [[0.2]],
        'metadatas': [[{"source": "c1"}]]
    }
    coll2 = MagicMock()
    coll2.query.return_value = {
        'documents': [["from_coll2"]],
        'distances': [[0.1]],
        'metadatas': [[{"source": "c2"}]]
    }
    mock_client.return_value.get_or_create_collection.side_effect = [coll1, coll2]

    with patch('langchain_ollama.OllamaEmbeddings') as mock_emb:
        mock_inst = MagicMock()
        mock_inst.embed_query.return_value = [0.1] * 384
        mock_emb.return_value = mock_inst
        result = retrieve_from_multiple_collections("query", ["c1", "c2"], top_k=5)
        assert "from_coll2" in result
        assert "from_coll1" in result