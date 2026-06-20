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


@patch("src.services.rag_retriever.store_chunks")
@patch("src.services.rag_retriever.retrieve_with_scores")
@patch("src.services.rag_retriever.retrieve_from_multiple_collections")
@patch("src.services.vector_store.get_chroma_client")
def test_build_rag_context_from_hashes_corrupted_collection(
    mock_client_factory, mock_retrieve_multi, mock_retrieve_scores, mock_store_chunks
):
    from src.services.rag_retriever import build_rag_context_from_hashes
    from src.services.vector_store import get_collection_name

    h = "a" * 64
    coll_name = get_collection_name(h)

    mock_client = MagicMock()
    mock_client.get_collection.return_value = MagicMock()
    mock_client.delete_collection.return_value = None
    mock_client_factory.return_value = mock_client

    mock_retrieve_scores.side_effect = Exception(
        "Internal error: Error creating hnsw segment reader: Nothing found on disk"
    )
    mock_retrieve_multi.return_value = "context from rebuild"

    with patch("src.models.ContentRegistry") as mock_cr, \
         patch("src.services.rag_retriever.chunk_text") as mock_chunk:
        mock_entry = MagicMock()
        mock_entry.extracted_text = "rebuild text for corrupted collection"
        mock_cr.query.filter_by.return_value.first.return_value = mock_entry
        mock_chunk.return_value = ["rebuild chunk 1", "rebuild chunk 2"]

        result = build_rag_context_from_hashes("test goal", [h])

    assert result == "context from rebuild"
    mock_client.delete_collection.assert_called_once_with(name=coll_name)
    mock_store_chunks.assert_called_once()


@patch("src.services.rag_retriever.retrieve_from_multiple_collections")
@patch("src.services.vector_store.get_chroma_client")
def test_build_rag_context_from_hashes_no_valid_collections(
    mock_client_factory, mock_retrieve_multi
):
    from src.services.rag_retriever import build_rag_context_from_hashes

    mock_client = MagicMock()
    mock_client.get_collection.side_effect = Exception("not found")
    mock_client_factory.return_value = mock_client

    with patch("src.models.ContentRegistry") as mock_cr:
        mock_cr.query.filter_by.return_value.first.return_value = None

        result = build_rag_context_from_hashes("test goal", ["b" * 64])

    assert result == ""
    mock_retrieve_multi.assert_not_called()


# ── Chroma Cloud backend toggle (CHROMA_DB) tests ──────────────────────


class TestChromaBackendSelection:
    """Tests for the CHROMA_DB=cloud toggle in get_chroma_client()."""

    def test_ci_forces_ephemeral_regardless_of_chroma_db(self, monkeypatch):
        """CI=true must always win, even if CHROMA_DB=cloud is set."""
        from src.services import vector_store

        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "fake-key")
        monkeypatch.setenv("CHROMA_CLOUD_CONNECTION_STRING", "fake-tenant")
        monkeypatch.setenv("CHROMA_COLLECTION_NAME", "fake-db")

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch("chromadb.EphemeralClient") as mock_eph, \
             patch("chromadb.PersistentClient") as mock_persist:
            mock_eph.return_value = MagicMock(name="ephemeral")
            vector_store.get_chroma_client()

        mock_cloud.assert_not_called()
        mock_persist.assert_not_called()
        mock_eph.assert_called_once()

    def test_cloud_creds_missing_reverts_to_local(self, monkeypatch):
        """CHROMA_DB=cloud with empty creds must fall back to local."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
        monkeypatch.delenv("CHROMA_CLOUD_CONNECTION_STRING", raising=False)

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_local.return_value = MagicMock(name="local")
            result = vector_store.get_chroma_client()

        mock_cloud.assert_not_called()
        mock_local.assert_called_once()
        assert result is mock_local.return_value

    def test_cloud_connection_string_empty_reverts_to_local(self, monkeypatch):
        """CHROMA_DB=cloud with empty connection string must fall back."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "fake-key")
        monkeypatch.delenv("CHROMA_CLOUD_CONNECTION_STRING", raising=False)

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_local.return_value = MagicMock(name="local")
            vector_store.get_chroma_client()

        mock_cloud.assert_not_called()
        mock_local.assert_called_once()

    def test_cloud_collection_name_empty_reverts_to_local(self, monkeypatch):
        """CHROMA_DB=cloud with empty collection name must fall back."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "fake-key")
        monkeypatch.setenv("CHROMA_CLOUD_CONNECTION_STRING", "fake-tenant")
        monkeypatch.setenv("CHROMA_COLLECTION_NAME", "")

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_local.return_value = MagicMock(name="local")
            vector_store.get_chroma_client()

        mock_cloud.assert_not_called()
        mock_local.assert_called_once()

    def test_cloud_client_construction_fails_reverts_to_local(self, monkeypatch):
        """If CloudClient() raises, fall back to local."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "bad-key")
        monkeypatch.setenv("CHROMA_CLOUD_CONNECTION_STRING", "bad-tenant")
        monkeypatch.setenv("CHROMA_COLLECTION_NAME", "bad-db")

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_cloud.side_effect = RuntimeError("auth failed")
            mock_local.return_value = MagicMock(name="local")
            result = vector_store.get_chroma_client()

        mock_cloud.assert_called_once()
        mock_local.assert_called_once()
        assert result is mock_local.return_value

    def test_cloud_heartbeat_fails_reverts_to_local(self, monkeypatch):
        """If heartbeat() (connectivity probe) fails, fall back to local."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "stale-key")
        monkeypatch.setenv("CHROMA_CLOUD_CONNECTION_STRING", "stale-tenant")
        monkeypatch.setenv("CHROMA_COLLECTION_NAME", "stale-db")

        mock_cloud_instance = MagicMock()
        mock_cloud_instance.heartbeat.side_effect = RuntimeError(
            "connection refused"
        )

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_cloud.return_value = mock_cloud_instance
            mock_local.return_value = MagicMock(name="local")
            result = vector_store.get_chroma_client()

        mock_cloud.assert_called_once()
        mock_cloud_instance.heartbeat.assert_called_once()
        mock_local.assert_called_once()
        assert result is mock_local.return_value

    def test_cloud_valid_returns_cloud_client(self, monkeypatch):
        """Valid creds + successful heartbeat -> CloudClient with correct args."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "valid-key")
        monkeypatch.setenv("CHROMA_CLOUD_CONNECTION_STRING", "valid-tenant")
        monkeypatch.setenv("CHROMA_COLLECTION_NAME", "valid-db")

        mock_cloud_instance = MagicMock()
        mock_cloud_instance.heartbeat.return_value = 12345

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_cloud.return_value = mock_cloud_instance
            result = vector_store.get_chroma_client()

        mock_cloud.assert_called_once_with(
            tenant="valid-tenant",
            database="valid-db",
            api_key="valid-key",
        )
        mock_cloud_instance.heartbeat.assert_called_once()
        mock_local.assert_not_called()
        assert result is mock_cloud_instance

    def test_local_default_when_chroma_db_unset(self, monkeypatch):
        """No CHROMA_DB -> local PersistentClient (the existing default)."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("CHROMA_DB", raising=False)

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_local.return_value = MagicMock(name="local")
            result = vector_store.get_chroma_client()

        mock_cloud.assert_not_called()
        mock_local.assert_called_once()
        assert result is mock_local.return_value

    def test_local_explicit_uses_local(self, monkeypatch):
        """CHROMA_DB=local -> local PersistentClient, no cloud attempt."""
        from src.services import vector_store

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("CHROMA_DB", "local")

        with patch("chromadb.CloudClient") as mock_cloud, \
             patch.object(vector_store, "_get_local_client") as mock_local:
            mock_local.return_value = MagicMock(name="local")
            result = vector_store.get_chroma_client()

        mock_cloud.assert_not_called()
        mock_local.assert_called_once()
        assert result is mock_local.return_value