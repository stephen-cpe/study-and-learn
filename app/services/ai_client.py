"""
AI client wrapper for interacting with Ollama or mock responses.
"""
import os
import requests


def call_ollama(prompt: str, model: str = None) -> str:
    """Call Ollama API to generate a response from a prompt.
    
    If AI_MOCK environment variable is set to 'true', returns a mock response.
    
    Args:
        prompt (str): The prompt to send to the AI model
        model (str): The model to use (defaults to OLLAMA_MODEL env var or qwen3:1.7b)
        
    Returns:
        str: The AI-generated response text
        
    TODO: replace mock with actual Ollama integration and error handling
    """
    # Check if we should use mock
    if os.environ.get('AI_MOCK', '').lower() == 'true':
        # Return a mock response for testing
        return f"Mock response for prompt: {prompt[:50]}..." if len(prompt) > 50 else f"Mock response for prompt: {prompt}"
    
    # Get model from environment variable or use default per SRS
    if model is None:
        model = os.environ.get('OLLAMA_MODEL', 'qwen3:1.7b')
    
    # Get base URL from environment, default to localhost
    base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    url = f"{base_url}/api/generate"
    
    # Prepare the payload
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    # Make the request
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        return result.get('response', '')
    except requests.exceptions.RequestException as e:
        # In a real app, we might want to log this and raise a custom exception
        # For now, we'll return an error message
        return f"Error calling Ollama: {str(e)}"