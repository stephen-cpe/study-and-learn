"""
Summary generation service for the Study-and-Learn MVP.
"""
import logging
from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError, StudyAndLearnError

logger = logging.getLogger(__name__)


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

    prompt = f"""You are an AI assistant that creates study summaries. 
Given the following extracted text from study materials, generate a concise summary that includes:

1. Main topics covered in the material
2. Suggested difficulty level (beginner, intermediate, advanced)
3. Potential prerequisites needed to understand the material
4. Key takeaways for a learner

Extracted Text:
{extracted_text}

Summary:"""

    try:
        summary = call_ollama(prompt)
        return summary.strip()
    except AIServiceError as e:
        logger.error("Summary generation failed: %s", str(e))
        raise StudyAndLearnError(
            "AI service is currently unavailable. Could not generate a summary. "
            "Please verify your AI backend is running and try again."
        ) from e
