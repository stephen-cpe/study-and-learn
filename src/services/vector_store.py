"""
Vector store service using ChromaDB.
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION_PREFIX = "doc_"
MAX_HASH_LENGTH = 59


def get_collection_name(file_hash: str) -> str:
    return f"{COLLECTION_PREFIX}{file_hash[:MAX_HASH_LENGTH]}"


def get_chroma_client():
    """Get ChromaDB client based on environment.
    
    Returns:
        Chroma client (Persistent or Ephemeral)
    """
    if os.environ.get('CI', '').lower() == 'true':
        import chromadb
        return chromadb.EphemeralClient()
    else:
        import chromadb
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'chroma_db')
        os.makedirs(data_dir, exist_ok=True)
        return chromadb.PersistentClient(path=data_dir)


def store_chunks(chunks: List[str], collection_name: str,
                 metadata: Optional[List[Dict[str, Any]]] = None) -> str:
    """Embed and store text chunks in ChromaDB.
    
    Args:
        chunks (List[str]): List of text chunks to store
        collection_name (str): Name for the collection
        metadata (Optional[List[Dict[str, Any]]]): Optional per-chunk metadata
        
    Returns:
        str: Status message
    """
    if not chunks:
        return "No chunks to store"
    
    client = get_chroma_client()
    
    try:
        collection = client.get_or_create_collection(name=collection_name)
        
        from langchain_ollama import OllamaEmbeddings
        embedding_model = OllamaEmbeddings(model=os.environ.get('OLLAMA_EMBEDDING_MODEL', 'qwen3-embedding:0.6b'))
        
        embeddings = embedding_model.embed_documents(chunks)
        
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        kwargs = {"ids": ids, "documents": chunks, "embeddings": embeddings}
        if metadata:
            kwargs["metadatas"] = metadata
        collection.add(**kwargs)
        
        return f"Stored {len(chunks)} chunks in collection '{collection_name}'"
    except Exception as e:
        logger.error("Failed to store chunks: %s", str(e))
        raise


def retrieve_context(query: str, collection_name: str, top_k: int = 5) -> str:
    """Retrieve relevant context using similarity search.
    
    Args:
        query (str): The query text (typically the learning goal)
        collection_name (str): Name of the collection to search
        top_k (int): Number of top results to retrieve
        
    Returns:
        str: Retrieved context joined as string
    """
    client = get_chroma_client()
    
    try:
        collection = client.get_or_create_collection(name=collection_name)
        
        from langchain_ollama import OllamaEmbeddings
        embedding_model = OllamaEmbeddings(model=os.environ.get('OLLAMA_EMBEDDING_MODEL', 'qwen3-embedding:0.6b'))
        
        query_embedding = embedding_model.embed_query(query)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        if results and results.get('documents') and results['documents'][0]:
            retrieved_docs = results['documents'][0]
            return "\n\n".join(retrieved_docs)
        return ""
    except Exception as e:
        logger.error("Failed to retrieve context: %s", str(e))
        raise


def retrieve_with_scores(query: str, collection_name: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve context with similarity scores.
    
    Args:
        query (str): The query text
        collection_name (str): Name of the collection to search
        top_k (int): Number of top results to retrieve
        
    Returns:
        List[Dict[str, Any]]: Results with 'document', 'score', 'metadata' keys
    """
    client = get_chroma_client()
    
    try:
        collection = client.get_or_create_collection(name=collection_name)
        
        from langchain_ollama import OllamaEmbeddings
        embedding_model = OllamaEmbeddings(model=os.environ.get('OLLAMA_EMBEDDING_MODEL', 'qwen3-embedding:0.6b'))
        
        query_embedding = embedding_model.embed_query(query)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "distances", "metadatas"]
        )
        
        output = []
        if results and results.get('documents') and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                entry = {'document': doc}
                if results.get('distances') and results['distances'][0]:
                    entry['score'] = 1.0 - results['distances'][0][i]
                else:
                    entry['score'] = 0.0
                if results.get('metadatas') and results['metadatas'][0]:
                    entry['metadata'] = results['metadatas'][0][i]
                output.append(entry)
        return output
    except Exception as e:
        logger.error("Failed to retrieve with scores: %s", str(e))
        raise


def retrieve_from_multiple_collections(
    query: str,
    collection_names: List[str],
    top_k: int = 5
) -> str:
    """Query multiple ChromaDB collections and merge results by similarity score.
    
    Args:
        query: The search query (learning goal)
        collection_names: List of collection names to query
        top_k: Number of top results to return total
    
    Returns:
        Joined top_k most relevant chunks across all collections.
    """
    all_results = []
    
    for coll_name in collection_names:
        try:
            results = retrieve_with_scores(query, coll_name, top_k=3)
            all_results.extend(results)
        except Exception as e:
            logger.warning("Failed to query collection '%s': %s", coll_name, str(e))
            continue
    
    if not all_results:
        return ""
    
    all_results.sort(key=lambda r: r.get('score', 0.0), reverse=True)
    top_results = all_results[:top_k]
    
    return "\n\n".join(r['document'] for r in top_results)


def retrieve_from_multiple_collections_with_sources(
    query: str,
    collection_names: List[str],
    top_k: int = 5
) -> Dict[str, Any]:
    """Query multiple collections and return context text + source metadata.

    Unlike ``retrieve_from_multiple_collections``, this function preserves
    chunk-level provenance (chunk ID, source hash, similarity score, and
    full chunk text) alongside the joined context string.

    Args:
        query: The search query.
        collection_names: ChromaDB collection names to query.
        top_k: Total number of top results across all collections.

    Returns:
        Dict with ``context_text`` (str) and ``sources`` (list of dicts
        each containing chunk_id, source_hash, score, and text).
    """
    all_results = []

    for coll_name in collection_names:
        try:
            results = retrieve_with_scores(query, coll_name, top_k=3)
            all_results.extend(results)
        except Exception as e:
            logger.warning("Failed to query collection '%s': %s", coll_name, str(e))
            continue

    if not all_results:
        return {"context_text": "", "sources": []}

    all_results.sort(key=lambda r: r.get('score', 0.0), reverse=True)
    top_results = all_results[:top_k]

    sources = []
    for r in top_results:
        metadata = r.get('metadata', {}) if isinstance(r.get('metadata'), dict) else {}
        sources.append({
            'chunk_id': metadata.get('chunk_id', ''),
            'source_hash': metadata.get('source_hash', ''),
            'score': r.get('score', 0.0),
            'text': r.get('document', ''),
        })

    context_text = "\n\n".join(r['document'] for r in top_results)
    return {"context_text": context_text, "sources": sources}
