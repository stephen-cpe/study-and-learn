"""
RAG retriever orchestrator service.
"""
import logging
import uuid
from typing import Any, Dict, List

from config_defaults import RAG_TOP_K_DEFAULT, env_int
from src.services.chunker import chunk_text
from src.services.vector_store import (
    get_collection_name,
    retrieve_context,
    retrieve_from_multiple_collections,
    retrieve_from_multiple_collections_with_sources,
    retrieve_with_scores,
    store_chunks,
)

logger = logging.getLogger(__name__)


def build_rag_context(goal: str, files_data: List[str]) -> str:
    """Orchestrate RAG pipeline: chunk, store, and retrieve context.
    
    Args:
        goal (str): The learning goal (used as query)
        files_data (List[str]): List of extracted text from uploaded files
        
    Returns:
        str: Retrieved context from RAG pipeline
    """
    if not files_data:
        return ""
    
    all_chunks = []
    
    for text in files_data:
        if text and text.strip():
            chunks = chunk_text(text)
            all_chunks.extend(chunks)
    
    if not all_chunks:
        return ""
    
    collection_name = f"study_{uuid.uuid4().hex[:8]}"
    
    try:
        store_chunks(all_chunks, collection_name)
        top_k = env_int('RAG_TOP_K', RAG_TOP_K_DEFAULT)
        context = retrieve_context(goal, collection_name, top_k=top_k)
        return context
    except Exception as e:
        logger.warning("RAG pipeline failed, falling back to concatenated text: %s", str(e))
        return ""


def _resolve_valid_collections(goal: str, file_hashes: List[str]) -> List[str]:
    """Discover, validate, and if needed rebuild the ChromaDB collections
    for the given file hashes.

    For each hash: if a ChromaDB collection exists, accept it; if not but
    ContentRegistry has cached text, chunk and embed it on-the-fly. Each
    discovered collection is then probed with a tiny retrieval — a
    collection whose index is corrupted (e.g. HNSW "Nothing found on
    disk") is deleted and rebuilt from ContentRegistry text before being
    accepted.

    Note: the ``ContentRegistry`` and ``get_chroma_client`` imports are
    deliberately function-level (call-time) so tests can patch them at
    their source modules.

    Args:
        goal: The learning goal (used as the probe query).
        file_hashes: List of SHA-256 hashes for uploaded files.

    Returns:
        List of valid collection names; empty when nothing could be
        discovered or rebuilt.
    """
    from src.models import ContentRegistry

    collection_names = []

    for h in file_hashes:
        coll_name = get_collection_name(h)
        try:
            from src.services.vector_store import get_chroma_client
            client = get_chroma_client()
            try:
                client.get_collection(name=coll_name)
                collection_names.append(coll_name)
                continue
            except Exception as e:
                logger.debug("Collection '%s' not found, will rebuild from registry: %s", coll_name, str(e))

            entry = ContentRegistry.query.filter_by(file_hash=h).first()
            if entry and entry.extracted_text:
                chunks = chunk_text(entry.extracted_text)
                if chunks:
                    chunk_metadata = [{"source_hash": h, "content_type": "text"} for _ in chunks]
                    store_chunks(chunks, coll_name, metadata=chunk_metadata)
                    collection_names.append(coll_name)
        except Exception as e:
            logger.warning("Skipping hash %s: %s", h[:8], str(e))

    if not collection_names:
        logger.warning("No ChromaDB collections found for any file hash, falling back")
        return []

    from src.services.vector_store import get_chroma_client as _get_client
    clean_client = _get_client()
    valid_names = []
    for coll_name in collection_names:
        try:
            retrieve_with_scores(goal, coll_name, top_k=1)
            valid_names.append(coll_name)
        except Exception as e:
            logger.warning(
                "Collection '%s' is corrupted (query failed), attempting rebuild: %s",
                coll_name[:40], str(e)
            )
            try:
                clean_client.delete_collection(name=coll_name)
            except Exception:
                pass
            for h in file_hashes:
                test_name = get_collection_name(h)
                if test_name == coll_name:
                    entry = ContentRegistry.query.filter_by(file_hash=h).first()
                    if entry and entry.extracted_text:
                        chunks = chunk_text(entry.extracted_text)
                        if chunks:
                            chunk_metadata = [{"source_hash": h, "content_type": "text"} for _ in chunks]
                            try:
                                store_chunks(chunks, coll_name, metadata=chunk_metadata)
                                valid_names.append(coll_name)
                            except Exception as rebuild_err:
                                logger.warning(
                                    "Failed to rebuild corrupted collection '%s': %s",
                                    coll_name[:40], str(rebuild_err)
                                )
                    break

    if not valid_names:
        logger.warning("No valid ChromaDB collections found for any file hash")
        return []

    return valid_names


def build_rag_context_from_hashes(goal: str, file_hashes: List[str], top_k: int = None) -> str:
    """Build RAG context by querying content-keyed ChromaDB collections.

    Collection discovery, corruption detection, and rebuilds are handled
    by :func:`_resolve_valid_collections`; this function then queries all
    valid collections and merges the results.

    Args:
        goal: The learning goal (used as retrieval query)
        file_hashes: List of SHA-256 hashes for uploaded files

    Returns:
        Merged RAG context from all relevant document collections.
    """
    if not file_hashes:
        return ""

    valid_names = _resolve_valid_collections(goal, file_hashes)
    if not valid_names:
        return ""

    try:
        context = retrieve_from_multiple_collections(goal, valid_names, top_k=top_k)
        return context
    except Exception as e:
        logger.warning("Multi-collection retrieval failed: %s", str(e))
        return ""


def build_rag_context_from_hashes_with_sources(
    goal: str, file_hashes: List[str], file_names: List[str] = None,
    top_k: int = None, exclude_chunks: set = None
) -> Dict[str, Any]:
    """Build RAG context with source provenance metadata.

    Like ``build_rag_context_from_hashes`` but returns a dict with both the
    joined context text and per-chunk source metadata including resolved
    filenames.

    Args:
        goal: The learning goal (used as retrieval query).
        file_hashes: SHA-256 hashes for uploaded files.
        file_names: Parallel list of original filenames, one per hash.
            Used to resolve human-readable names in source entries.

    Returns:
        Dict with ``context_text`` (str) and ``sources`` (list of dicts
        each containing chunk_id, source_hash, score, text, filename).
    """
    if not file_hashes:
        return {"context_text": "", "sources": []}

    hash_to_name: Dict[str, str] = {}
    if file_names:
        for h, name in zip(file_hashes, file_names):
            if h and name:
                hash_to_name[h] = name

    valid_names = _resolve_valid_collections(goal, file_hashes)
    if not valid_names:
        return {"context_text": "", "sources": []}

    try:
        result = retrieve_from_multiple_collections_with_sources(goal, valid_names, top_k=top_k)
        if exclude_chunks:
            filtered_sources = []
            filtered_docs = []
            for source in result.get("sources", []):
                chunk_id = source.get("chunk_id", "")
                if chunk_id and chunk_id in exclude_chunks:
                    continue
                filtered_sources.append(source)
                filtered_docs.append(source.get("text", ""))
            result["sources"] = filtered_sources
            result["context_text"] = "\n\n".join(filtered_docs)
        for source in result.get("sources", []):
            sh = source.get("source_hash", "")
            source["filename"] = hash_to_name.get(sh, sh[:12] + "...")
        return result
    except Exception as e:
        logger.warning("Multi-collection retrieval with sources failed: %s", str(e))
        return {"context_text": "", "sources": []}