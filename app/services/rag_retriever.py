"""
RAG retriever orchestrator service.
"""
import logging
import uuid
from typing import List
from app.services.chunker import chunk_text
from app.services.vector_store import store_chunks, retrieve_context

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