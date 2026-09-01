"""
Tests for the LLM JSON extraction helper and fallback-quiz improvements.

Covers four fixes for the "fallback quiz fires on real lessons" bug:

    1. Shared extract_json helper (strips markdown fences, uses
       raw_decode, logs failures instead of silently swallowing them).
    2. JSON mode at the Ollama API level (format: "json" in the payload).
    3. Topic-aware fallback quiz (references module_title + slide content
       instead of a hardcoded generic study-skills list).
    4. Fallback flag surfaced to the user (generate_quiz returns
       ``fallback: True`` so the route can flash a warning).
"""
import json
import logging
from unittest.mock import MagicMock, patch

from src.services.llm_json import extract_json
from src.services.quiz_generator import _fallback_quiz, generate_quiz

# ═══════════════════════════════════════════════════════════════════════
# 1. extract_json helper
# ═══════════════════════════════════════════════════════════════════════


class TestExtractJson:
    """extract_json must handle the common LLM response pathologies that
    the old find('{')...rfind('}')+1 pattern failed on."""

    def test_plain_json(self):
        assert extract_json('{"key": "value"}') == {'key': 'value'}

    def test_json_with_leading_prose(self):
        resp = 'Here is the quiz:\n{"questions": [{"id": "q1"}]}'
        assert extract_json(resp) == {'questions': [{'id': 'q1'}]}

    def test_json_with_trailing_prose(self):
        resp = '{"questions": [{"id": "q1"}]}\n\nLet me know if you need more.'
        assert extract_json(resp) == {'questions': [{'id': 'q1'}]}

    def test_json_in_markdown_code_fence(self):
        resp = '```json\n{"questions": [{"id": "q1"}]}\n```'
        assert extract_json(resp) == {'questions': [{'id': 'q1'}]}

    def test_json_in_bare_code_fence(self):
        resp = '```\n{"questions": [{"id": "q1"}]}\n```'
        assert extract_json(resp) == {'questions': [{'id': 'q1'}]}

    def test_json_with_nested_objects(self):
        resp = '{"questions": [{"options": ["A", "B"]}], "meta": {"count": 1}}'
        result = extract_json(resp)
        assert result['meta']['count'] == 1
        assert result['questions'][0]['options'] == ['A', 'B']

    def test_truncated_json_returns_none(self):
        """If the JSON is truncated (timeout mid-generation), extract_json
        must return None rather than raising."""
        resp = '{"questions": [{"id": "q1", "prompt": "Wha'
        assert extract_json(resp) is None

    def test_empty_string_returns_none(self):
        assert extract_json('') is None

    def test_no_json_returns_none(self):
        assert extract_json('I cannot help with that.') is None

    def test_logs_warning_on_failure(self, caplog):
        with caplog.at_level(logging.WARNING):
            extract_json('not json at all')
        assert any('Failed to extract JSON' in r.message for r in caplog.records)

    def test_logs_warning_on_truncated(self, caplog):
        with caplog.at_level(logging.WARNING):
            extract_json('{"questions": [')
        assert any('Failed to extract JSON' in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════
# 2. JSON mode at the API level
# ═══════════════════════════════════════════════════════════════════════


class TestJsonMode:
    """call_ollama must pass format='json' to the Ollama API so the
    model is constrained to valid JSON output."""

    @patch('src.services.ai_client.requests.post')
    def test_local_client_sends_format_json(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={'response': '{"ok": true}'})
        )
        mock_post.return_value.raise_for_status = MagicMock()

        from src.services.ai_client import _call_ollama_local
        _call_ollama_local('test prompt')

        payload = mock_post.call_args[1]['json']
        assert payload.get('format') == 'json', (
            "local Ollama payload must include format='json' so the model "
            "is constrained to valid JSON output"
        )

    @patch('src.services.ai_client_cloud.requests.post')
    def test_cloud_client_sends_response_format_json(self, mock_post, monkeypatch):
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('OLLAMA_CLOUD_API_KEY', 'fake-key')
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                'choices': [{'message': {'content': '{"ok": true}'}}]
            })
        )
        mock_post.return_value.raise_for_status = MagicMock()

        from src.services.ai_client_cloud import call_ollama as cloud_call
        cloud_call('test prompt')

        call_args = mock_post.call_args
        assert call_args is not None, "requests.post was not called"
        payload = call_args.kwargs.get('json') if call_args.kwargs else call_args[1].get('json')
        assert payload is not None
        fmt = payload.get('response_format') or payload.get('format')
        assert fmt is not None, (
            "cloud payload must include response_format or format for JSON mode"
        )


# ═══════════════════════════════════════════════════════════════════════
# 3. Topic-aware fallback quiz
# ═══════════════════════════════════════════════════════════════════════


class TestTopicAwareFallback:
    """_fallback_quiz must reference the module title and slide content,
    not a hardcoded generic study-skills list."""

    def test_fallback_references_module_title(self):
        result = _fallback_quiz(5, module_title='Cell Biology')
        prompts = ' '.join(q['prompt'] for q in result['questions'])
        assert 'Cell Biology' in prompts or 'cell' in prompts.lower(), (
            "fallback quiz should reference the module title, not generic "
            "study-skills content"
        )

    def test_fallback_references_slide_content(self):
        slides = [
            {'type': 'content', 'heading': 'Mitochondria',
             'bullets': ['Mitochondria produce ATP', 'ATP is energy']}
        ]
        result = _fallback_quiz(5, module_title='Cell Biology', slides=slides)
        prompts = ' '.join(q['prompt'] for q in result['questions'])
        assert 'mitochondria' in prompts.lower() or 'atp' in prompts.lower(), (
            "fallback quiz should reference slide content, not generic "
            "study-skills content"
        )

    def test_fallback_without_slides_still_works(self):
        result = _fallback_quiz(3, module_title='History')
        assert len(result['questions']) == 3

    def test_fallback_without_title_still_works(self):
        result = _fallback_quiz(3)
        assert len(result['questions']) == 3

    def test_fallback_questions_are_valid_structure(self):
        result = _fallback_quiz(5, module_title='Physics',
                                slides=[{'type': 'content', 'heading': 'Gravity',
                                         'bullets': ['Gravity pulls things down']}])
        for q in result['questions']:
            assert 'type' in q
            assert 'prompt' in q
            assert 'explanation' in q
            if q['type'] in ('mcq', 'cloze_dropdown'):
                assert 'options' in q
                assert 'answer_index' in q
                assert len(q['options']) >= 3
            elif q['type'] == 'true_false':
                assert 'answer' in q
            elif q['type'] == 'multi_select':
                assert 'options' in q
                assert 'answer_indices' in q

    def test_fallback_does_not_use_old_hardcoded_questions(self):
        """The old fallback had these exact prompts — none should appear."""
        old_prompts = [
            'Last-minute cramming is the most effective way',
            'Understanding core concepts is essential',
            'What is the most effective way to learn new material?',
            'Which of the following are effective study techniques?',
            'actively retrieving information from memory is called',
        ]
        result = _fallback_quiz(5, module_title='Cell Biology',
                                slides=[{'type': 'content', 'heading': 'Cells',
                                         'bullets': ['Cells are basic']}])
        prompts = ' '.join(q['prompt'] for q in result['questions']).lower()
        for old in old_prompts:
            assert old.lower() not in prompts, (
                f"Old hardcoded fallback prompt should not appear: {old!r}"
            )


# ═══════════════════════════════════════════════════════════════════════
# 4. Fallback flag surfaced to the user
# ═══════════════════════════════════════════════════════════════════════


class TestFallbackFlag:
    """generate_quiz must return a ``fallback: True`` flag when the AI
    fails and the fallback quiz is used, so the route can flash a warning
    to the user instead of silently showing generic questions."""

    def test_generate_quiz_sets_fallback_on_ai_error(self, monkeypatch):
        """When call_ollama raises AIServiceError, generate_quiz returns
        the fallback quiz with fallback=True."""
        import src.services.quiz_generator as qg
        from src.services.exceptions import AIServiceError

        def fail(prompt, **kwargs):
            raise AIServiceError("AI is down")

        monkeypatch.setattr(qg, 'call_ollama', fail)
        result = generate_quiz("Cell Biology", [], None, n_questions=5)
        assert result.get('fallback') is True, (
            "generate_quiz must set fallback=True when AI fails"
        )
        assert 'questions' in result

    def test_generate_quiz_sets_fallback_on_unparseable_json(self, monkeypatch):
        """When the LLM returns unparseable text, generate_quiz returns
        the fallback quiz with fallback=True."""
        import src.services.quiz_generator as qg

        def garbage(prompt, **kwargs):
            return "I cannot generate a quiz for this topic."

        monkeypatch.setattr(qg, 'call_ollama', garbage)
        result = generate_quiz("Cell Biology", [], None, n_questions=5)
        assert result.get('fallback') is True

    def test_generate_quiz_sets_fallback_on_empty_validation(self, monkeypatch):
        """When the LLM returns valid JSON but no valid questions,
        generate_quiz returns the fallback quiz with fallback=True."""
        import src.services.quiz_generator as qg

        def empty_json(prompt, **kwargs):
            return '{"questions": []}'

        monkeypatch.setattr(qg, 'call_ollama', empty_json)
        result = generate_quiz("Cell Biology", [], None, n_questions=5)
        assert result.get('fallback') is True

    def test_generate_quiz_no_fallback_flag_on_success(self, monkeypatch):
        """When the AI returns valid questions, fallback must NOT be set."""
        import src.services.quiz_generator as qg

        def good(prompt, **kwargs):
            return json.dumps({
                'questions': [
                    {'id': 'q1', 'type': 'mcq', 'prompt': 'What is a cell?',
                     'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                     'explanation': 'E'}
                ]
            })

        monkeypatch.setattr(qg, 'call_ollama', good)
        result = generate_quiz("Cell Biology", [], None, n_questions=1)
        assert result.get('fallback') is not True, (
            "generate_quiz must NOT set fallback=True on success"
        )