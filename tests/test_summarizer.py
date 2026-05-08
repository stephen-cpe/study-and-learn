"""
Unit tests for the summarizer service.
"""
import os
import pytest
from app.services.summarizer import generate_summary


def test_generate_summary_with_mock(monkeypatch):
    """Test that summarizer works with AI_MOCK=true."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # Test with sample extracted text
    extracted_text = "This is a sample text about machine learning. It covers supervised and unsupervised learning."
    summary = generate_summary(extracted_text)
    
    # Should return a string
    assert isinstance(summary, str)
    # Should not be empty
    assert summary != ''
    # Should contain some indication it's a summary (based on our mock)
    assert 'summary' in summary.lower() or 'mock' in summary.lower()


def test_generate_summary_prompt_construction(monkeypatch):
    """Test that the summarizer constructs the prompt correctly."""
    # Set environment variable to mock
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    # We'll mock the call_ollama function to capture what prompt is passed
    # Since summarizer imports call_ollama directly, we need to patch it in the summarizer module
    import app.services.summarizer as summarizer_module
    captured_prompt = {}
    
    def mock_call_ollama(prompt, model="llama3"):
        captured_prompt['prompt'] = prompt
        captured_prompt['model'] = model
        return "Mock summary response"
    
    monkeypatch.setattr(summarizer_module, 'call_ollama', mock_call_ollama)
    
    # Test with sample text
    extracted_text = "Sample text about Python programming."
    generate_summary(extracted_text)
    
    # Verify that a prompt was constructed and passed to call_ollama
    assert 'prompt' in captured_prompt
    prompt = captured_prompt['prompt']
    assert isinstance(prompt, str)
    # The prompt should contain the extracted text
    assert extracted_text in prompt
    # Should contain instructions for summary
    assert 'summary' in prompt.lower()
    # Should mention key topics or similar
    assert 'key topic' in prompt.lower() or 'main topic' in prompt.lower()