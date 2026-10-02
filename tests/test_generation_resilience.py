"""Tests for the generation-resilience work (quality-audit remediation).

Covers:
  * ``llm_json.generate_json`` — retry/repair on parse failure.
  * Lesson/quiz generators — repair success, anti-fabrication prompt,
    exact-slide contract, and concept-level dedup input.
  * Fail-closed degradation — ``lesson_content_status`` / ``is_lesson_degraded``,
    the grade-route 409, blocked path completion, and retake regeneration.
  * AI client decoding parameters (temperature / output bound).
"""
import json
import tempfile
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, User
from src.services import llm_json

# ═══════════════════════════════════════════════════════════════════════
# 1. generate_json retry/repair
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateJsonRepair:
    def test_succeeds_first_attempt(self):
        calls = []

        def call(prompt):
            calls.append(prompt)
            return '{"ok": true}'

        result = llm_json.generate_json('task', call)
        assert result == {'ok': True}
        assert len(calls) == 1

    def test_repairs_after_parse_failure(self, monkeypatch):
        """A garbage first response must be re-prompted, not degraded."""
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('LLM_JSON_REPAIR_ATTEMPTS', '2')
        calls = []

        def call(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return 'Here is the lesson, hope you like it!'
            return '{"slides": [{"type": "content"}]}'

        result = llm_json.generate_json(
            'task', call, parse_fn=lambda r: llm_json.extract_json(r),
            schema_hint='{"slides": []}', label='test',
        )
        assert result == {'slides': [{'type': 'content'}]}
        assert len(calls) == 2
        # The repair prompt must instruct the model to return ONLY JSON.
        assert 'not valid JSON' in calls[1]
        assert 'ONLY the JSON object' in calls[1]

    def test_returns_none_after_exhausting_attempts(self, monkeypatch):
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('LLM_JSON_REPAIR_ATTEMPTS', '1')
        calls = []

        def call(prompt):
            calls.append(prompt)
            return 'still not json'

        result = llm_json.generate_json('task', call)
        assert result is None
        assert len(calls) == 2  # initial + 1 repair

    def test_single_attempt_under_ai_mock(self, monkeypatch):
        """AI_MOCK returns a deterministic stub — retrying cannot help."""
        monkeypatch.setenv('AI_MOCK', 'true')
        calls = []

        def call(prompt):
            calls.append(prompt)
            return 'Mock response for prompt: ...'

        result = llm_json.generate_json('task', call)
        assert result is None
        assert len(calls) == 1

    def test_backend_exception_propagates(self):
        from src.services.exceptions import AIServiceError

        def call(prompt):
            raise AIServiceError('down')

        with pytest.raises(AIServiceError):
            llm_json.generate_json('task', call)

    def test_log_bad_response_handles_empty(self, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            llm_json.log_bad_response('', reason='empty')
        assert any('empty' in r.message for r in caplog.records)


class TestJsonEscapeSanitizer:
    """The audit's RMD failure mode: valid JSON structurally, but LaTeX
    single-backslash escapes (\\%) make json.loads fail. extract_json must
    recover these without altering already-valid JSON."""

    def test_invalid_latex_escape_is_recovered(self):
        bad = '{"bullets": ["MCF must stay above $98.5\\%$ for nominal"]}'
        import json as _json
        # Sanity: the raw text is genuinely invalid JSON.
        with pytest.raises(_json.JSONDecodeError):
            _json.loads(bad)
        result = llm_json.extract_json(bad)
        assert result is not None
        assert '98.5\\%' in result['bullets'][0]

    def test_valid_escapes_are_preserved(self):
        import json as _json
        good = r'{"a": "line1\nline2", "u": "\u00e9", "b": "\\ok"}'
        assert llm_json.sanitize_json_escapes(good) == good
        assert _json.loads(llm_json.sanitize_json_escapes(good)) == _json.loads(good)

    def test_fenced_latex_response_is_recovered(self):
        bad = ('```json\n'
               '{"slides": [{"type": "content", "heading": "H", '
               '"bullets": ["$94\\%$ threshold"]}]}\n```')
        result = llm_json.extract_json(bad)
        assert result is not None
        assert result['slides'][0]['bullets'] == ['$94\\%$ threshold']

    def test_backslash_outside_string_untouched(self):
        # No strings -> no escaping should occur.
        assert llm_json.sanitize_json_escapes('123 \\ 456') == '123 \\ 456'

    def test_array_extraction_recovers_latex(self):
        bad = ('[{"slide_index": 0, "text": "Above $98.5\\%$ is nominal."}]')
        result = llm_json.extract_json_array(bad)
        assert result is not None
        assert '98.5\\%' in result[0]['text']


class TestLatexEscapeAbsorption:
    """LaTeX commands starting with a valid JSON escape letter (\\text,
    \\times, \\frac, \\tan) parse silently as control chars unless
    detected. extract_json must preserve the LaTeX and inject no control
    characters, while leaving genuine escapes untouched."""

    @pytest.mark.parametrize('raw,expected', [
        (r'{"b": ["at $T+0.0\text{s}$"]}', r'$T+0.0\text{s}$'),
        (r'{"b": ["$847\text{ TB/s}$"]}', r'$847\text{ TB/s}$'),
        (r'{"b": ["$\frac{1}{2}$"]}', r'$\frac{1}{2}$'),
        (r'{"b": ["$\times$ and $\tan\theta$"]}', r'$\times$'),
        (r'{"b": ["$5.0\ \mu\text{Sv}$"]}', r'$5.0\ \mu\text{Sv}$'),
        (r'{"b": ["$94.0\% \text{--} 98.5\%$"]}',
         r'$94.0\% \text{--} 98.5\%$'),
    ])
    def test_latex_command_not_absorbed(self, raw, expected):
        result = llm_json.extract_json(raw)
        assert result is not None
        got = result['b'][0]
        assert expected in got, f"expected {expected!r} in {got!r}"
        for ctrl in ('\t', '\b', '\f', '\r'):
            assert ctrl not in got, f"control char {ctrl!r} leaked into {got!r}"

    def test_valid_escapes_still_work_when_mixed_with_latex(self):
        raw = r'{"a": "line1\nline2", "b": ["$x\text{y}$"]}'
        result = llm_json.extract_json(raw)
        assert result is not None
        assert result['a'] == 'line1\nline2'
        assert result['b'][0] == r'$x\text{y}$'

    def test_genuine_tab_and_newline_preserved(self):
        raw = '{"a": "col1\\tcol2", "b": "row1\\nrow2"}'
        result = llm_json.extract_json(raw)
        assert result == {'a': 'col1\tcol2', 'b': 'row1\nrow2'}

    def test_standalone_short_escape_not_false_positived(self):
        # "a\tb" where b is not a known command must stay a tab.
        raw = r'{"a": "x\ty"}'
        result = llm_json.extract_json(raw)
        assert result == {'a': 'x\ty'}


# ═══════════════════════════════════════════════════════════════════════
# 2. Generator prompts + repair integration
# ═══════════════════════════════════════════════════════════════════════


def _make_capturing_ollama(responses):
    """Return a call_fn that yields the given responses in order."""
    calls = []

    def call(prompt):
        calls.append(prompt)
        idx = min(len(calls) - 1, len(responses) - 1)
        return responses[idx]

    call.calls = calls
    return call


class TestLessonGeneratorResilience:
    def test_repair_recovers_a_parse_failure(self, monkeypatch):
        """The RMD failure mode: first response unparseable, repair works."""
        import src.services.lesson_generator as lg
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('LLM_JSON_REPAIR_ATTEMPTS', '2')
        fake = _make_capturing_ollama([
            'The lesson could not be generated as JSON. Sorry!',
            json.dumps({
                'module_title': 'MCF',
                'slides': [
                    {'type': 'title', 'title': 'MCF', 'subtitle': 'Intro'},
                    {'type': 'content', 'heading': 'Failure',
                     'bullets': ['<50% forms a black hole']},
                    {'type': 'summary', 'bullets': ['Review thresholds']},
                ],
            }),
        ])
        monkeypatch.setattr(lg, 'call_ollama', fake)

        out = lg.generate_lesson('MCF', 'Learn MCF', None)
        assert out['fallback'] is False
        assert len(out['slides']) == 3


    def test_degrades_after_repair_attempts_fail(self, monkeypatch):
        import src.services.lesson_generator as lg
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('LLM_JSON_REPAIR_ATTEMPTS', '1')
        monkeypatch.setattr(
            lg, 'call_ollama',
            lambda prompt, *a, **k: 'not json at all')
        out = lg.generate_lesson('MCF', 'Learn MCF', None)
        assert out['fallback'] is True
        assert out['fallback_reason'] == 'parse_error'


    def test_prompt_requests_exactly_six_slides(self, monkeypatch):
        import src.services.lesson_generator as lg
        monkeypatch.setenv('AI_MOCK', 'true')
        captured = {}
        monkeypatch.setattr(
            lg, 'call_ollama',
            lambda prompt, *a, **k: captured.setdefault('p', prompt) or
            '{"module_title":"T","slides":[{"type":"title","title":"T","subtitle":"S"}]}')
        lg.generate_lesson('T', 'G', None)
        assert 'Generate exactly 6 slides' in captured['p']


    def test_prompt_contains_anti_fabrication_rule(self, monkeypatch):
        import src.services.lesson_generator as lg
        monkeypatch.setenv('AI_MOCK', 'true')
        captured = {}
        monkeypatch.setattr(
            lg, 'call_ollama',
            lambda prompt, *a, **k: captured.setdefault('p', prompt) or
            '{"module_title":"T","slides":[{"type":"title","title":"T","subtitle":"S"}]}')
        lg.generate_lesson('T', 'G', None)
        p = captured['p']
        assert 'TERMINOLOGY RULE' in p
        assert 'Never invent or rename' in p


    def test_prompt_lists_already_taught_concepts(self, monkeypatch):
        import src.services.lesson_generator as lg
        monkeypatch.setenv('AI_MOCK', 'true')
        captured = {}
        monkeypatch.setattr(
            lg, 'call_ollama',
            lambda prompt, *a, **k: captured.setdefault('p', prompt) or
            '{"module_title":"T","slides":[{"type":"title","title":"T","subtitle":"S"}]}')
        lg.generate_lesson('T', 'G', None,
                           covered_concepts=['Module 1: MFA', 'Privileged accounts'])
        p = captured['p']
        assert 'ALREADY TAUGHT' in p
        assert 'Module 1: MFA' in p
        assert 'Privileged accounts' in p


class TestQuizGeneratorResilience:
    def test_quiz_repair_recovers(self, monkeypatch):
        import src.services.quiz_generator as qg
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('LLM_JSON_REPAIR_ATTEMPTS', '2')
        good = json.dumps({'questions': [
            {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
             'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
             'explanation': 'E'}]})
        fake = _make_capturing_ollama(['oops, no json here', good])
        monkeypatch.setattr(qg, 'call_ollama', fake)
        out = qg.generate_quiz('MCF', [], None, n_questions=1)
        assert out.get('fallback') is not True
        assert out['questions'][0]['prompt'] == 'P?'


# ═══════════════════════════════════════════════════════════════════════
# 3. Fail-closed content status
# ═══════════════════════════════════════════════════════════════════════


class TestContentStatus:
    def test_ready_when_flags_absent(self):
        from src.services.lesson_orchestrator import (
            is_lesson_degraded,
            lesson_content_status,
        )
        lesson = {'lesson': {'slides': []}, 'quiz': {'questions': []}}
        assert lesson_content_status(lesson) == 'ready'
        assert is_lesson_degraded(lesson) is False

    def test_degraded_when_lesson_fallback(self):
        from src.services.lesson_orchestrator import is_lesson_degraded
        assert is_lesson_degraded({'lesson': {'fallback': True}}) is True

    def test_degraded_when_quiz_fallback(self):
        from src.services.lesson_orchestrator import is_lesson_degraded
        assert is_lesson_degraded({'quiz': {'fallback': True}}) is True

    def test_explicit_status_wins(self):
        from src.services.lesson_orchestrator import lesson_content_status
        # Explicit ready overrides a stale quiz fallback flag.
        assert lesson_content_status(
            {'content_status': 'ready', 'quiz': {'fallback': True}}) == 'ready'
        assert lesson_content_status(
            {'content_status': 'degraded'}) == 'degraded'

    def test_non_dict_is_degraded(self):
        from src.services.lesson_orchestrator import is_lesson_degraded
        assert is_lesson_degraded(None) is True


# ═══════════════════════════════════════════════════════════════════════
# 4. Route-level fail-closed behavior
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def resilience_client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('AI_MOCK', 'true')
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(cache_dir=temp_dir, threshold=500, mode=0o700),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.extensions.pop('sqlalchemy', None)
        db.init_app(app)
        with app.app_context():
            db.create_all()
            user = User(username='resilient', email='r@example.com',
                        can_generate_lessons=True, tts_enabled=False,
                        lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _seed_path(app, user, degraded=False, passed=False):
    with app.app_context():
        from src.repositories.lesson_repo import create_study_path
        path = create_study_path(user, 'T', 'G',
                                 modules=[{'title': 'M1'}],
                                 summary='S', relevance_result={})
        lessons = [{
            'index': 0, 'module_title': 'M1', 'estimated_effort': '1h',
            'lesson': {'slides': [{'type': 'title', 'title': 'T'}],
                       'fallback': degraded},
            'quiz': {'questions': [
                {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                 'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                 'explanation': 'E'}]},
            'checkpoints': {}, 'sources': [], 'difficulty': 'Normal',
            'tts_enabled': False, 'completed': passed, 'score': 100 if passed else None,
            'passed': passed,
            'content_status': 'degraded' if degraded else 'ready',
        }]
        from src.repositories.lesson_repo import save_lessons
        save_lessons(lessons, user, path_id=path.id)
        return path.id


def _login(client, username='resilient'):
    client.post('/login', data={'username': username, 'password': 'pass'})


class TestFailClosedGrade:
    def test_degraded_final_grade_rejected(self, resilience_client):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=True)
        with app.test_client() as c:
            _login(c)
            resp = c.post(f'/lessons/0/grade?path_id={path_id}',
                          json={'answers': [0], 'checkpoint_answers': {}})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['degraded'] is True
        assert data['needs_regeneration'] is True

    def test_degraded_checkpoint_only_still_allowed(self, resilience_client):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=True)
        with app.test_client() as c:
            _login(c)
            resp = c.post(f'/lessons/0/grade?path_id={path_id}',
                          json={'answers': [], 'checkpoint_answers': {}})
        assert resp.status_code == 200

    def test_ready_module_grades_normally(self, resilience_client):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=False)
        with app.test_client() as c:
            _login(c)
            resp = c.post(f'/lessons/0/grade?path_id={path_id}',
                          json={'answers': [0], 'checkpoint_answers': {}})
        assert resp.status_code == 200
        assert resp.get_json()['passed'] is True

    def test_complete_blocked_for_degraded_path(self, resilience_client):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=True, passed=True)
        with app.test_client() as c:
            _login(c)
            resp = c.post(f'/study-path/{path_id}/complete',
                          follow_redirects=True)
        assert b'module(s) failed to generate' in resp.data.lower()
        with app.app_context():
            assert db.session.get(StudyPath, path_id).status == 'active'

    def test_complete_allowed_for_ready_path(self, resilience_client):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=False, passed=True)
        with app.test_client() as c:
            _login(c)
            resp = c.post(f'/study-path/{path_id}/complete',
                          follow_redirects=True)
        assert b'marked as complete' in resp.data.lower()
        with app.app_context():
            assert db.session.get(StudyPath, path_id).status == 'completed'

    def test_lessons_page_flags_degraded_module(self, resilience_client):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=True)
        with app.test_client() as c:
            _login(c)
            body = c.get(f'/lessons?path_id={path_id}').get_data(as_text=True)
        assert 'Content Failed' in body
        assert 'Regenerate Lesson' in body

    def test_retake_regenerates_degraded_slides(self, resilience_client, monkeypatch):
        """A degraded module's retake must regenerate slides, not reuse the
        placeholder (reusing would keep the learner stuck forever)."""
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=True)
        import src.routes.lessons as lessons_mod
        seen = {}

        def fake_build(module, goal, retriever, **kwargs):
            seen['existing_slides'] = kwargs.get('existing_slides')
            return {
                'lesson': {'module_title': 'M1',
                           'slides': [{'type': 'title', 'title': 'Fresh'}],
                           'fallback': False, 'narration': []},
                'quiz': {'questions': [], 'fallback': False},
                'checkpoints': {}, 'sources': [],
            }

        monkeypatch.setattr(lessons_mod, 'build_module_artifacts', fake_build)
        with app.test_client() as c:
            _login(c)
            resp = c.post(f'/lessons/0/retake?path_id={path_id}',
                          json={})
        assert resp.status_code == 200
        assert seen['existing_slides'] is None, (
            "Degraded retake must NOT reuse placeholder slides")

    def test_retake_reuses_slides_when_ready(self, resilience_client, monkeypatch):
        app, user = resilience_client
        path_id = _seed_path(app, user, degraded=False)
        import src.routes.lessons as lessons_mod
        seen = {}

        def fake_build(module, goal, retriever, **kwargs):
            seen['existing_slides'] = kwargs.get('existing_slides')
            return {
                'lesson': {'module_title': 'M1', 'slides': [], 'fallback': False,
                           'narration': []},
                'quiz': {'questions': [], 'fallback': False},
                'checkpoints': {}, 'sources': [],
            }

        monkeypatch.setattr(lessons_mod, 'build_module_artifacts', fake_build)
        with app.test_client() as c:
            _login(c)
            c.post(f'/lessons/0/retake?path_id={path_id}', json={})
        assert seen['existing_slides'] is not None


class TestFallbackRateObservability:
    def test_generation_summary_logs_degraded_count(
            self, resilience_client, caplog, monkeypatch):
        """The worker must emit one structured generation_summary line with
        the fallback rate so degraded content is trackable/alertable."""
        import logging
        app, user = resilience_client

        def fake_build(module, goal, retriever, **kwargs):
            return {
                'lesson': {'module_title': module['title'],
                           'slides': [{'type': 'title', 'title': 'T'}],
                           'fallback': True, 'fallback_reason': 'parse_error',
                           'narration': []},
                'quiz': {'questions': [], 'fallback': False},
                'checkpoints': {}, 'sources': [],
            }

        monkeypatch.setattr(
            'src.services.lesson_orchestrator.build_module_artifacts',
            fake_build)
        with app.app_context():
            from src.repositories.lesson_repo import create_study_path
            path = create_study_path(user, 'T', 'G',
                                     modules=[{'title': 'M1'}, {'title': 'M2'}],
                                     summary='S', relevance_result={})
            from src.services import background_tasks as _bt
            from src.services import progress_tracker
            from src.services.generation_worker import run_generation_for_path
            progress_tracker.create_task(task_id='obs-task', display_name='u')
            _bt.create_task('obs-task', user.id, kind='generate', label='t')
            with caplog.at_level(logging.INFO):
                run_generation_for_path(
                    app, user.id, path.id,
                    {'learning_goal': 'G', 'study_title': 'T',
                     'modules': [{'title': 'M1'}, {'title': 'M2'}],
                     'existing_lessons': [], 'extracted_texts': [],
                     'file_hashes': [], 'file_names': [],
                     'content_digest': '', 'tts_enabled': False,
                     'tts_speaker': 'Ava', 'difficulty': 'Normal',
                     'display_name': 'u'},
                    'obs-task')
        summary = [r for r in caplog.records
                   if 'generation_summary' in r.getMessage()]
        assert summary, "worker must log a generation_summary line"
        msg = summary[0].getMessage()
        assert 'degraded=2' in msg
        assert 'fallback_rate=1.00' in msg
        assert 'parse_error' in msg


# ═══════════════════════════════════════════════════════════════════════
# 5. AI client decoding parameters
# ═══════════════════════════════════════════════════════════════════════


class TestDecodingParameters:
    @patch('src.services.ai_client.requests.post')
    def test_local_payload_sets_temperature_and_num_predict(self, mock_post):
        from unittest.mock import MagicMock
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={'response': '{"ok": true}',
                                         'done_reason': 'stop'}))
        mock_post.return_value.raise_for_status = MagicMock()
        from src.services.ai_client import _call_ollama_local
        _call_ollama_local('test prompt')
        options = mock_post.call_args[1]['json']['options']
        assert 'temperature' in options
        assert 'num_predict' in options
        assert options['temperature'] <= 0.5

    @patch('src.services.ai_client_cloud.requests.post')
    def test_cloud_payload_sets_temperature_and_max_tokens(
            self, mock_post, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.delenv('AI_MOCK', raising=False)
        monkeypatch.setenv('OLLAMA_CLOUD_API_KEY', 'fake')
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                'choices': [{'message': {'content': '{"ok": true}'},
                             'finish_reason': 'stop'}]}))
        mock_post.return_value.raise_for_status = MagicMock()
        from src.services.ai_client_cloud import call_ollama as cloud_call
        cloud_call('test prompt')
        payload = mock_post.call_args[1]['json']
        assert 'temperature' in payload
        assert 'max_tokens' in payload
