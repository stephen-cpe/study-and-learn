"""
Curriculum/study path generation service for the Study-and-Learn MVP.
"""
import json
import logging
from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError, StudyAndLearnError

logger = logging.getLogger(__name__)


def generate_study_path(learning_goal: str, extracted_text: str, summary: str) -> dict:
    """Generate a structured study path based on learning goal and document content.

    Constructs a prompt for a sequenced module list with estimated effort per module.

    Args:
        learning_goal (str): The learner's stated learning goal
        extracted_text (str): The text extracted from uploaded documents
        summary (str): The AI-generated summary of the documents

    Returns:
        dict: Contains a 'modules' key with a list of module dictionaries,
              each having 'title' and 'estimated_effort' keys
    """
    if not learning_goal or not learning_goal.strip():
        return {
            'modules': [{'title': 'Please provide a learning goal', 'estimated_effort': 'N/A'}]
        }

    if not extracted_text or not extracted_text.strip():
        return {
            'modules': [{'title': 'Please upload study materials', 'estimated_effort': 'N/A'}]
        }

    prompt = f"""You are an AI assistant that creates structured study plans.
Based on the following information, generate a recommended study path:

Learning Goal: {learning_goal}

Extracted Text from Documents: {extracted_text}

Summary of Documents: {summary}

Create a sequenced study plan with modules/lessons. For each module, provide:
1. A clear, descriptive title
2. Estimated effort to complete (e.g., "2 hours", "1 week", "3 days")

Provide your study plan in the following JSON format:
{{
  "modules": [
    {{
      "title": "Module 1 Title",
      "estimated_effort": "Time estimate"
    }},
    {{
      "title": "Module 2 Title", 
      "estimated_effort": "Time estimate"
    }}
    // ... additional modules as needed
  ]
}}

Study Plan:"""

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Study path generation failed: %s", str(e))
        raise StudyAndLearnError(
            "AI service is currently unavailable. Could not generate a study path. "
            "Please verify your AI backend is running and try again."
        ) from e

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)

            if 'modules' in result and isinstance(result['modules'], list):
                validated_modules = []
                for module in result['modules']:
                    if isinstance(module, dict) and 'title' in module and 'estimated_effort' in module:
                        validated_modules.append({
                            'title': str(module['title']),
                            'estimated_effort': str(module['estimated_effort'])
                        })

                if validated_modules:
                    return {'modules': validated_modules}
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    return {
        'modules': [{
            'title': 'Review the provided materials',
            'estimated_effort': '1-2 hours'
        }]
    }
