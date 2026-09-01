"""
Curriculum/study path generation service for the Study-and-Learn MVP.
"""
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

    prompt = f"""You are an expert educator that creates structured study plans.
Based on the following information, generate a recommended study path:

Learning Goal: {learning_goal}

Extracted Text from Documents: {extracted_text}

Summary of Documents: {summary}

MODULE SCALING RULES:
1. Scale the number of modules to the breadth of the document content AND the
   specificity of the learning goal. Fewer pages or a narrow/specific goal
   means fewer modules. More content or a broad goal means more modules.
2. For a short document (under 10 pages) or a very specific learning goal,
   create 2-4 modules. For a medium document (10-50 pages), create 4-7 modules.
   For a large document (50+ pages), create 5-10 modules. Never exceed 10 modules.
3. If the document does not contain enough content to justify multiple modules,
   create fewer modules rather than padding with repetitive content.

ANTI-OVERLAP RULES:
4. Each module MUST cover a DISTINCT topic or concept. Do NOT create modules
   that overlap in content — if two modules would teach the same concept,
   merge them into one.
5. Sequence modules so that each builds on the previous one without repeating
   it. Module N+1 should introduce NEW concepts, not rehash Module N.
6. If the learning goal is very specific (e.g., "Learn about X algorithm"),
   focus the modules on that specific topic rather than creating a broad
   survey of the entire document.

For each module, provide:
1. A clear, descriptive title that reflects its DISTINCT content
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

    from src.services.llm_json import extract_json
    result = extract_json(response)
    if result and 'modules' in result and isinstance(result['modules'], list):
        validated_modules = []
        for module in result['modules']:
            if isinstance(module, dict) and 'title' in module and 'estimated_effort' in module:
                validated_modules.append({
                    'title': str(module['title']),
                    'estimated_effort': str(module['estimated_effort'])
                })

        if validated_modules:
            return {'modules': validated_modules}

    return {
        'modules': [{
            'title': 'Review the provided materials',
            'estimated_effort': '1-2 hours'
        }]
    }
