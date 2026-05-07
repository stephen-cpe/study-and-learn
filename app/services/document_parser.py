"""
Document parser service for extracting text from uploaded files.
"""
import os


def extract_text(file_path: str) -> str:
    """Extract text from a file based on its extension.
    
    Currently supports .txt and .md files.
    
    Args:
        file_path (str): Path to the file to extract text from
        
    Returns:
        str: The extracted text content
        
    Raises:
        ValueError: If file is empty, not found, or unsupported type
    """
    # Check if file exists
    if not os.path.exists(file_path):
        raise ValueError('File not found')
    
    # Check if file is empty
    if os.path.getsize(file_path) == 0:
        raise ValueError('File is empty')
    
    # Get file extension
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    # Read file based on extension
    if ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    elif ext == '.md':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        # TODO: strip basic markdown if trivial, otherwise return raw
        # For now, we return raw content as per spec: "otherwise return raw"
        # We'll implement trivial markdown stripping in a future update.
    else:
        raise ValueError(f'Unsupported file type: {ext}')
    
    return text