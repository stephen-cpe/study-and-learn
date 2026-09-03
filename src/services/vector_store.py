"""
Vector store service using ChromaDB.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from config_defaults import (
    EMBEDDING_MODEL_DEFAULT,
    RAG_TOP_K_DEFAULT,
    env_default,
    env_int,
)

logger = logging.getLogger(__name__)

COLLECTION_PREFIX = "doc_"
MAX_HASH_LENGTH = 59


def _per_collection_top_k(top_k: int | None) -> int:
    """Return the per-collection retrieval depth.

    The caller passes the *total* ``top_k`` it wants across all collections.
    Each individual collection is queried with a deeper ``per-collection``
    depth so the merged-and-sorted result can actually fill the budget
    (instead of being starved by an arbitrary per-collection cap).  The
    default scales with ``OLLAMA_NUM_CTX`` via :func:`rag_budget.get_top_k_for_budget`.
    """
    if top_k is not None:
        return max(1, top_k)
    from src.services.rag_budget import get_top_k_for_budget
    return get_top_k_for_budget(
        per_collection_top_k=env_int('RAG_TOP_K', RAG_TOP_K_DEFAULT)
    )


def get_collection_name(file_hash: str) -> str:
    return f"{COLLECTION_PREFIX}{file_hash[:MAX_HASH_LENGTH]}"


def _get_local_client():
    """Build the default local PersistentClient.

    Centralized so the cloud fallback path can reuse it without
    duplicating the path-resolution logic.
    """
    import chromadb
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'data', 'chroma_db'
    )
    os.makedirs(data_dir, exist_ok=True)
    return chromadb.PersistentClient(path=data_dir)


def _try_cloud_client():
    """Attempt to build a Chroma Cloud client from env credentials.

    Returns a chromadb CloudClient on success, or None on any failure
    (missing/empty credentials, client construction error, heartbeat
    probe failure). Every failure path logs a clear, actionable message
    so developers can diagnose misconfiguration.

    The caller is responsible for falling back to the local client.
    """
    import chromadb

    api_key = os.environ.get("CHROMA_CLOUD_API_KEY", "").strip()
    connection_string = os.environ.get(
        "CHROMA_CLOUD_CONNECTION_STRING", ""
    ).strip()
    database = os.environ.get(
        "CHROMA_COLLECTION_NAME", "study-and-learn-chromadb"
    ).strip()

    # ── Validate required credentials ────────────────────────────────
    missing = []
    if not api_key:
        missing.append("CHROMA_CLOUD_API_KEY")
    if not connection_string:
        missing.append("CHROMA_CLOUD_CONNECTION_STRING")
    if not database:
        missing.append("CHROMA_COLLECTION_NAME")
    if missing:
        logger.error(
            "CHROMA_DB=cloud requested but required credential(s) are "
            "empty/unset: %s. Reverting to local PersistentClient. "
            "Set these in your .env to use Chroma Cloud.",
            ", ".join(missing),
        )
        return None

    # ── Attempt client construction + connectivity probe ──────────────
    try:
        logger.info(
            "Connecting to Chroma Cloud (tenant=%s, database=%s)",
            connection_string[:8] + "...", database,
        )
        client = chromadb.CloudClient(
            tenant=connection_string,
            database=database,
            api_key=api_key,
        )
        # Lightweight connectivity/auth probe. heartbeat() hits the
        # server and raises on bad credentials or unreachable host.
        client.heartbeat()
        logger.info("Chroma Cloud connection established.")
        return client
    except Exception as e:
        logger.error(
            "Chroma Cloud connection failed (CHROMA_DB=cloud): %s. "
            "Reverting to local PersistentClient. Verify "
            "CHROMA_CLOUD_API_KEY, CHROMA_CLOUD_CONNECTION_STRING, "
            "and CHROMA_COLLECTION_NAME are valid.",
            str(e),
        )
        return None


def get_chroma_client():
    """Get ChromaDB client based on environment.

    Precedence (highest first):
      1. CI=true           -> EphemeralClient (in-memory, never network)
      2. CHROMA_DB=cloud    -> CloudClient (validates creds + heartbeat;
                                falls back to local on any failure)
      3. otherwise / fallback -> PersistentClient (local disk, the default)

    Returns:
        Chroma client (Ephemeral, Cloud, or Persistent).
    """
    # ── 1. CI always wins: keep tests isolated and offline ──────────
    if os.environ.get('CI', '').lower() == 'true':
        import chromadb
        return chromadb.EphemeralClient()

    # ── 2. Cloud backend (opt-in, with graceful fallback) ───────────
    chroma_db = os.environ.get('CHROMA_DB', 'local').strip().lower()
    if chroma_db == 'cloud':
        cloud_client = _try_cloud_client()
        if cloud_client is not None:
            return cloud_client
        # Fall through to local on any cloud failure.
        logger.warning(
            "Chroma Cloud unavailable; using local PersistentClient."
        )

    # ── 3. Default: local persistent client ─────────────────────────
    return _get_local_client()


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
        embedding_model = OllamaEmbeddings(model=env_default('OLLAMA_EMBEDDING_MODEL', EMBEDDING_MODEL_DEFAULT))
        
        embeddings = embedding_model.embed_documents(chunks)
        
        ids = [f"chunk_{i}" for i in range(len(chunks))]

        # Inject chunk_id into each chunk's metadata so the retrieval
        # layer can return it for cross-module dedup filtering
        # (used_chunk_ids / exclude_chunks). Without this field in
        # metadata, retrieve_from_multiple_collections_with_sources
        # reads metadata.get('chunk_id', '') which is always '' and the
        # dedup never matches — modules can repeat the same chunks.
        #
        # chunk_id is namespaced by collection name so the same integer
        # position in two different files never collides (e.g. chunk_0
        # of file A and chunk_0 of file B are distinct).  This is
        # critical for the exclude_chunks filter to be correct across
        # multiple uploaded files.
        if metadata:
            # Merge chunk_id into the caller-supplied metadata dicts
            # without overwriting the caller's keys.
            enriched = []
            for i, m in enumerate(metadata):
                d = dict(m) if isinstance(m, dict) else {}
                d.setdefault('chunk_id', f"{collection_name}:{ids[i]}")
                enriched.append(d)
            metadata = enriched
        else:
            metadata = [
                {'chunk_id': f"{collection_name}:{cid}"} for cid in ids
            ]

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
        embedding_model = OllamaEmbeddings(model=env_default('OLLAMA_EMBEDDING_MODEL', EMBEDDING_MODEL_DEFAULT))
        
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
        embedding_model = OllamaEmbeddings(model=env_default('OLLAMA_EMBEDDING_MODEL', EMBEDDING_MODEL_DEFAULT))
        
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
    top_k: int = None,
    max_chars: int = None
) -> str:
    """Query multiple ChromaDB collections and merge results by similarity score.

    Each collection is queried at a deeper *per-collection* depth (see
    :func:`_per_collection_top_k`) so the merged results can actually fill
    the total budget instead of being starved by an arbitrary cap.  A
    character budget then trims the merged list to what can actually fit in
    the model's context window.

    Args:
        query: The search query (learning goal)
        collection_names: List of collection names to query
        top_k: Number of top results to return *total* across all
            collections.  If None, uses ``RAG_TOP_K`` scaled by the
            available context budget (see :mod:`rag_budget`).
        max_chars: Hard cap on the returned joined text length in
            characters.  If None, derived from the context budget.

    Returns:
        Joined top_k most relevant chunks across all collections.
    """
    per_coll_k = _per_collection_top_k(top_k)
    all_results = []

    for coll_name in collection_names:
        try:
            results = retrieve_with_scores(query, coll_name, top_k=per_coll_k)
            all_results.extend(results)
        except Exception as e:
            logger.warning("Failed to query collection '%s': %s", coll_name, str(e))
            continue

    if not all_results:
        return ""

    all_results.sort(key=lambda r: r.get('score', 0.0), reverse=True)
    total_top_k_max = env_int('RAG_TOP_K', RAG_TOP_K_DEFAULT)
    top_results = all_results[:total_top_k_max]

    # Enforce character budget so the merged context actually fits in the
    # model's context window.  Chunks are dropped from the tail (lowest
    # relevance) until the joined length is within budget.
    if max_chars is None:
        from src.services.rag_budget import get_context_budget_chars
        max_chars = get_context_budget_chars()
    kept: list[str] = []
    running = 0
    for r in top_results:
        doc = r.get('document', '') or ''
        doc_len = len(doc)
        if running + doc_len > max_chars:
            break
        kept.append(doc)
        running += doc_len

    return "\n\n".join(kept)


def retrieve_from_multiple_collections_with_sources(
    query: str,
    collection_names: List[str],
    top_k: int = None,
    max_chars: int = None
) -> Dict[str, Any]:
    """Query multiple collections and return context text + source metadata.

    Unlike ``retrieve_from_multiple_collections``, this function preserves
    chunk-level provenance (chunk ID, source hash, similarity score, and
    full chunk text) alongside the joined context string.  The same
    per-collection depth and character budgeting apply.

    Args:
        query: The search query.
        collection_names: ChromaDB collection names to query.
        top_k: Total number of top results across all collections. If None,
            uses ``RAG_TOP_K`` scaled by the available context budget.
        max_chars: Hard cap on the returned joined context_text length in
            characters.  If None, derived from the context budget.

    Returns:
        Dict with ``context_text`` (str) and ``sources`` (list of dicts
        each containing chunk_id, source_hash, score, and text).
    """
    per_coll_k = _per_collection_top_k(top_k)
    all_results = []

    for coll_name in collection_names:
        try:
            results = retrieve_with_scores(query, coll_name, top_k=per_coll_k)
            all_results.extend(results)
        except Exception as e:
            logger.warning("Failed to query collection '%s': %s", coll_name, str(e))
            continue

    if not all_results:
        return {"context_text": "", "sources": []}

    all_results.sort(key=lambda r: r.get('score', 0.0), reverse=True)
    total_top_k_max = env_int('RAG_TOP_K', RAG_TOP_K_DEFAULT)
    top_results = all_results[:total_top_k_max]

    # Enforce character budget so the merged context actually fits in the
    # model's context window, keeping the highest-relevance chunks.
    if max_chars is None:
        from src.services.rag_budget import get_context_budget_chars
        max_chars = get_context_budget_chars()
    kept_results = []
    running = 0
    for r in top_results:
        doc = r.get('document', '') or ''
        doc_len = len(doc)
        if running + doc_len > max_chars:
            break
        kept_results.append(r)
        running += doc_len

    sources = []
    for r in kept_results:
        metadata = r.get('metadata', {}) if isinstance(r.get('metadata'), dict) else {}
        sources.append({
            'chunk_id': metadata.get('chunk_id', ''),
            'source_hash': metadata.get('source_hash', ''),
            'score': r.get('score', 0.0),
            'text': r.get('document', ''),
        })

    context_text = "\n\n".join(r['document'] for r in kept_results)
    return {"context_text": context_text, "sources": sources}
