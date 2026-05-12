"""
Summary generation service for the Study-and-Learn MVP.
"""
from src.services.ai_client import call_ollama


def generate_summary(extracted_text: str) -> str:
    """Generate a structured summary of the extracted text.
    
    Creates a prompt targeting key topics, difficulty level, and prerequisites
    as specified in FR-013 and FR-014.
    
    Args:
        extracted_text (str): The text extracted from uploaded documents
        
    Returns:
        str: A generated summary covering main topics, difficulty, and prerequisites
    """
    if not extracted_text or not extracted_text.strip():
        return "No text provided for summarization."
    
    # Construct a structured prompt for summary generation
    # This prompt is designed to elicit:
    # - Main topics covered (FR-013)
    # - Possible prerequisites or difficulty level (FR-014)
    prompt = f"""You are an AI assistant that creates study summaries. 
Given the following extracted text from study materials, generate a concise summary that includes:

1. Main topics covered in the material
2. Suggested difficulty level (beginner, intermediate, advanced)
3. Potential prerequisites needed to understand the material
4. Key takeaways for a learner

Extracted Text:
{extracted_text}

Summary:"""
    
    # Call the AI service to generate the summary
    summary = call_ollama(prompt)
    
    # Clean up the response (remove any extra whitespace)
    return summary.strip()