"""
RAG retriever orchestrator service.
"""
import logging
import uuid
from typing import List
from src.services.chunker import chunk_text
from src.services.vector_store import store_chunks, retrieve_context, retrieve_from_multiple_collections, get_collection_name

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
        context = retrieve_context(goal, collection_name, top_k=5)
        return context
    except Exception as e:
        logger.warning("RAG pipeline failed, falling back to concatenated text: %s", str(e))
        return ""


def build_rag_context_from_hashes(goal: str, file_hashes: List[str]) -> str:
    """Build RAG context by querying content-keyed ChromaDB collections.
    
    For each file hash, checks if a ChromaDB collection exists. If it does,
    queries it. If it doesn't but ContentRegistry has cached text, chunks
    and embeds it on-the-fly. Then queries all collections and merges results.
    
    Args:
        goal: The learning goal (used as retrieval query)
        file_hashes: List of SHA-256 hashes for uploaded files
    
    Returns:
        Merged RAG context from all relevant document collections.
    """
    from src.models import ContentRegistry

    if not file_hashes:
        return ""

    collection_names = []

    for h in file_hashes:
        coll_name = get_collection_name(h)
        client = None
        try:
            from src.services.vector_store import get_chroma_client
            client = get_chroma_client()
            try:
                client.get_collection(name=coll_name)
                collection_names.append(coll_name)
                continue
            except Exception:
                pass

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
        return ""

    try:
        context = retrieve_from_multiple_collections(goal, collection_names, top_k=5)
        return context
    except Exception as e:
        logger.warning("Multi-collection retrieval failed: %s", str(e))
        return ""
