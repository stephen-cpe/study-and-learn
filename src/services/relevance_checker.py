"""
Relevance checking service for the Study-and-Learn MVP.
"""
import json
from src.services.ai_client import call_ollama


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
        
    TODO: replace mock with actual response parsing logic
    """
    # Handle empty inputs
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
    
    # Construct a structured prompt for relevance checking
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
    
    # Call the AI service to get the relevance assessment
    response = call_ollama(prompt)
    
    # Try to parse the JSON response
    try:
        # Extract JSON from the response (in case there's extra text)
        # Look for content between curly braces
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)
            
            # Validate that we have the expected keys
            if all(key in result for key in ['relevance_label', 'explanation', 'missing_material']):
                # Ensure relevance_label is one of the expected values
                if result['relevance_label'] not in ['strong', 'partial', 'weak']:
                    result['relevance_label'] = 'weak'  # Default fallback
                return result
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    
    # Fallback if JSON parsing fails
    return {
        'relevance_label': 'partial',  # Default to partial if we can't parse
        'explanation': 'Unable to parse AI response, defaulting to partial relevance',
        'missing_material': 'Please try again or check the AI service'
    }