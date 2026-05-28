"""
Relevance checking service for the Study-and-Learn MVP.
"""
import json
import logging
from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError, StudyAndLearnError

logger = logging.getLogger(__name__)


def check_relevance(learning_goal: str, extracted_text: str, summary: str) -> dict:
    """Check the relevance between learning goal and document content.

    Constructs a prompt requesting a relevance label (strong/partial/weak),
    brief explanation, and missing material suggestions.

    Args:
        learning_goal (str): The learner's stated learning goal
        extracted_text (str): The text extracted from uploaded documents
        summary (str): The AI-generated summary of the documents

    Returns:
        dict: Contains relevance_label, explanation, and missing_material
    """
    if not learning_goal or not learning_goal.strip():
        return {
            'relevance_label': 'weak',
            'explanation': 'No learning goal provided',
            'missing_material': 'Please provide a learning goal'
        }

    if not extracted_text or not extracted_text.strip():
        return {
            'relevance_label': 'weak',
            'explanation': 'No document text provided',
            'missing_material': 'Please upload study materials'
        }

    prompt = f"""You are an AI assistant that checks relevance between learning goals and study materials.
Analyze the following:

Learning Goal: {learning_goal}

Extracted Text from Documents: {extracted_text}

Summary of Documents: {summary}

Provide your analysis in the following JSON format:
{{
  "relevance_label": "strong" or "partial" or "weak",
  "explanation": "Brief explanation of the relevance assessment",
  "missing_material": "Suggestions for what missing material would improve the match"
}}

Analysis:"""

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Relevance check failed: %s", str(e))
        raise StudyAndLearnError(
            "AI service is currently unavailable. Could not check material relevance. "
            "Please verify your AI backend is running and try again."
        ) from e

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)

            if all(key in result for key in ['relevance_label', 'explanation', 'missing_material']):
                if result['relevance_label'] not in ['strong', 'partial', 'weak']:
                    result['relevance_label'] = 'weak'
                return result
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    return {
        'relevance_label': 'partial',
        'explanation': 'Unable to parse AI response, defaulting to partial relevance',
        'missing_material': 'Please try again or check the AI service'
    }
