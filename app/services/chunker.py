"""
Text chunking service using LangChain.
"""
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(text: str) -> List[str]:
    """Split text into overlapping chunks using LangChain's RecursiveCharacterTextSplitter.
    
    Args:
        text (str): The text to chunk
        
    Returns:
        List[str]: List of text chunks
    """
    if not text or not text.strip():
        return []
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    chunks = splitter.split_text(text)
    return chunks