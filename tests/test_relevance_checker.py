"""
Unit tests for the relevance checker service.
"""
import os
import pytest
from src.services.relevance_checker import check_relevance


def test_check_relevance_with_mock(monkeypatch):
    """Test that check_relevance works with AI_MOCK=true."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # Test with sample inputs
    learning_goal = "Learn about machine learning"
    extracted_text = "This document discusses machine learning algorithms."
    summary = "This is a summary about machine learning."

    result = check_relevance(learning_goal, extracted_text, summary)
    
    # Should return a dictionary
    assert isinstance(result, dict)
    # Should have the expected keys
    assert 'relevance_label' in result
    assert 'explanation' in result
    assert 'missing_material' in result
    # Values should be strings
    assert isinstance(result['relevance_label'], str)
    assert isinstance(result['explanation'], str)
    assert isinstance(result['missing_material'], str)


def test_check_relevance_prompt_construction(monkeypatch):
    """Test that the relevance checker constructs the prompt correctly."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # We'll mock the call_ollama function to capture what prompt is passed
    # Since relevance_checker imports call_ollama directly, we need to patch it in the relevance_checker module
    import src.services.relevance_checker as relevance_checker_module
    captured_prompt = {}
    
    def mock_call_ollama(prompt, model="llama3"):
        captured_prompt['prompt'] = prompt
        captured_prompt['model'] = model
        # Return a mock response that the relevance checker can parse
        return '{"relevance_label": "strong", "explanation": "Good match", "missing_material": "None"}'
    
    monkeypatch.setattr(relevance_checker_module, 'call_ollama', mock_call_ollama)
    
    # Test with sample inputs
    learning_goal = "Learn about machine learning"
    extracted_text = "This document discusses machine learning algorithms."
    summary = "This is a summary about machine learning."
    check_relevance(learning_goal, extracted_text, summary)
    
    # Verify that a prompt was constructed and passed to call_ollama
    assert 'prompt' in captured_prompt
    prompt = captured_prompt['prompt']
    assert isinstance(prompt, str)
    # The prompt should contain the learning goal, extracted text, and summary
    assert learning_goal in prompt
    assert extracted_text in prompt
    assert summary in prompt
    # Should contain instructions for relevance checking
    assert 'relevance' in prompt.lower()
    # Should mention the expected output format (JSON)
    assert 'json' in prompt.lower() or 'label' in prompt.lower()