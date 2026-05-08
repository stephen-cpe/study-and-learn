"""
Document parser service for extracting text from uploaded files.
"""
import os


def extract_text(file_path: str) -> str:
    """Extract text from a file based on its extension.
    
    Supports .txt, .md, .pdf, and .docx files.
    
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
    if ext == '.txt' or ext == '.md':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    elif ext == '.pdf':
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text = ''
            for page in reader.pages:
                text += page.extract_text() + '\n'
        except Exception as e:
            raise ValueError(f'Failed to extract text from PDF: {str(e)}')
    elif ext == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
        except Exception as e:
            raise ValueError(f'Failed to extract text from DOCX: {str(e)}')
    else:
        raise ValueError(f'Unsupported file type: {ext}')
    
    # Check if any text was extracted
    if not text or not text.strip():
        raise ValueError('No readable text found in file')
    
    return text