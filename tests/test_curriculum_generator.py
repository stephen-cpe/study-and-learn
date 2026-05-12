"""
Unit tests for the curriculum generator service.
"""
import os
import pytest
from src.services.curriculum_generator import generate_study_path


def test_generate_study_path_with_mock(monkeypatch):
    """Test that generate_study_path works with AI_MOCK=true."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # Test with sample inputs
    learning_goal = "Learn about machine learning"
    extracted_text = "This document discusses machine learning algorithms."
    summary = "This is a summary about machine learning covering supervised and unsupervised learning."

    result = generate_study_path(learning_goal, extracted_text, summary)
    
    # Should return a dictionary
    assert isinstance(result, dict)
    # Should have the expected keys
    assert 'modules' in result
    # Modules should be a list
    assert isinstance(result['modules'], list)
    # Each module should have title and estimated_effort
    if len(result['modules']) > 0:
        module = result['modules'][0]
        assert 'title' in module
        assert 'estimated_effort' in module


def test_generate_study_path_prompt_construction(monkeypatch):
    """Test that the curriculum generator constructs the prompt correctly."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # We'll mock the call_ollama function to capture what prompt is passed
    # Since curriculum_generator imports call_ollama directly, we need to patch it in the curriculum_generator module
    import src.services.curriculum_generator as curriculum_generator_module
    captured_prompt = {}
    
    def mock_call_ollama(prompt, model="llama3"):
        captured_prompt['prompt'] = prompt
        captured_prompt['model'] = model
        # Return a mock response that the curriculum generator can parse
        return '{"modules": [{"title": "Introduction to ML", "estimated_effort": "2 hours"}, {"title": "Supervised Learning", "estimated_effort": "3 hours"}]}'
    
    monkeypatch.setattr(curriculum_generator_module, 'call_ollama', mock_call_ollama)
    
    # Test with sample inputs
    learning_goal = "Learn about machine learning"
    extracted_text = "This document discusses machine learning algorithms."
    summary = "This is a summary about machine learning."
    generate_study_path(learning_goal, extracted_text, summary)
    
    # Verify that a prompt was constructed and passed to call_ollama
    assert 'prompt' in captured_prompt
    prompt = captured_prompt['prompt']
    assert isinstance(prompt, str)
    # The prompt should contain the learning goal, extracted text, and summary
    assert learning_goal in prompt
    assert extracted_text in prompt
    assert summary in prompt
    # Should contain instructions for study path generation
    assert 'study path' in prompt.lower() or 'curriculum' in prompt.lower()
    # Should mention modules or lessons
    assert 'module' in prompt.lower() or 'lesson' in prompt.lower()