"""
Vector store service using ChromaDB.
"""
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


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


def store_chunks(chunks: List[str], collection_name: str) -> str:
    """Embed and store text chunks in ChromaDB.
    
    Args:
        chunks (List[str]): List of text chunks to store
        collection_name (str): Name for the collection
        
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
        collection.add(ids=ids, documents=chunks, embeddings=embeddings)
        
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