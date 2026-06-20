"""
Tests for mascot-error.gif surfacing on failure paths.

Verifies that mark_error is called in the three error surfaces:
  A. processing.py — document processing failures (AI down, parse fail)
  B. lessons.py    — lesson generation failures (AI down mid-generation)
  C. tts_worker.py — TTS failures (already covered in test_tts_worker.py)

The mascot-error.gif is the user-facing visual signal that something
went wrong. Without these mark_error calls, the mascot stays stuck
in 'busy' state during failures, misleading the user into thinking
the app is still working.
"""
import io
import json
import tempfile
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User
from src.services import progress_tracker
from src.services.progress_tracker import (
    GENERATE_STAGES,
    create_task as pt_create_task,
    get_progress as pt_get_progress,
)


@pytest.fixture
def error_client(monkeypatch):
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
            user = User(username='errortester', email='err@example.com',
                        can_generate_lessons=True, lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app.test_client() as c:
                c.post('/login', data={'username': 'errortester', 'password': 'pass'})
                yield c, app, user
            db.session.remove()
            db.drop_all()


@pytest.fixture
def tts_error_client(monkeypatch):
    """Like error_client but with tts_enabled=True from the start,
    so the generate-lessons route enters the TTS spawn block."""
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
            user = User(username='ttserrortester', email='ttserr@example.com',
                        can_generate_lessons=True, lesson_difficulty='Normal',
                        tts_enabled=True, tts_speaker='Ava')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app.test_client() as c:
                c.post('/login', data={'username': 'ttserrortester', 'password': 'pass'})
                yield c, app, user
            db.session.remove()
            db.drop_all()


# ── Surface A: processing.py ─────────────────────────────────────────

@patch('src.routes.processing.generate_summary')
def test_processing_failure_publishes_mascot_error(mock_summary, error_client):
    """When document processing fails with a StudyAndLearnError, the
    route must call mark_error so the mascot-error.gif is shown.
    """
    from src.services.exceptions import AIServiceError
    c, app, user = error_client

    mock_summary.side_effect = AIServiceError('AI model unreachable')

    task_id = 'proc-error-task-1'
    data = {
        'learning_goal': 'Learn testing',
        'files': [(io.BytesIO(b'Test content'), 'test.txt')],
        'task_id': task_id,
    }
    with patch("src.services.vision_parser.is_content_registered", return_value=None), \
         patch("src.services.vision_parser.register_content"):
        response = c.post('/process', data=data, content_type='multipart/form-data')

    assert response.status_code == 500
    # The mascot must be in error state.
    progress = pt_get_progress(task_id)
    # cleanup_task may have run; if so, the entry is gone. We check
    # BEFORE cleanup by inspecting the response — but mark_error is
    # called BEFORE cleanup_task, so the cache write happened. If
    # cleanup deleted it, we can't assert directly. Instead, patch
    # cleanup_task to verify mark_error was called first.
    # For a robust assertion, we re-run with cleanup patched.
    assert progress is None or progress.get('mascot_state') == 'error', (
        f"Unexpected progress state: {progress}"
    )


@patch('src.routes.processing.generate_summary')
def test_processing_failure_calls_mark_error_before_cleanup(mock_summary, error_client, monkeypatch):
    """mark_error must be called BEFORE cleanup_task so the error
    cosmetic is visible to the JS poll even briefly. We patch
    cleanup_task to be a no-op so we can inspect the entry."""
    from src.services.exceptions import AIServiceError
    c, app, user = error_client

    mock_summary.side_effect = AIServiceError('AI model unreachable')

    # Prevent cleanup from deleting the entry so we can assert.
    monkeypatch.setattr(progress_tracker, 'cleanup_task', lambda *a, **kw: None)

    task_id = 'proc-error-task-2'
    data = {
        'learning_goal': 'Learn testing',
        'files': [(io.BytesIO(b'Test content'), 'test.txt')],
        'task_id': task_id,
    }
    with patch("src.services.vision_parser.is_content_registered", return_value=None), \
         patch("src.services.vision_parser.register_content"):
        response = c.post('/process', data=data, content_type='multipart/form-data')

    assert response.status_code == 500
    progress = pt_get_progress(task_id)
    assert progress is not None, "mark_error was not called before cleanup"
    assert progress['mascot_state'] == 'error', (
        f"mascot_state={progress.get('mascot_state')!r}; expected 'error'"
    )
    assert progress.get('error') is True


# ── Surface B: lessons.py generate route ─────────────────────────────

@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_generate_lessons_failure_publishes_mascot_error(
    mock_quiz, mock_lesson, error_client, monkeypatch,
):
    """When lesson generation fails mid-loop with an uncaught error
    (e.g. a non-AIServiceError that the generators don't swallow),
    the route must call mark_error so the mascot-error.gif is shown.

    Note: AIServiceError is caught by lesson_generator.py and returns
    a fallback lesson, so it never reaches the route's except. We use
    a generic RuntimeError to bypass the generator's catch.
    """
    c, app, user = error_client

    # Use RuntimeError — lesson_generator only catches AIServiceError,
    # so RuntimeError propagates to the route's try/except.
    mock_lesson.side_effect = RuntimeError('Unexpected DB failure mid-generation')
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })

    # Prevent cleanup from deleting the entry.
    monkeypatch.setattr(progress_tracker, 'cleanup_task', lambda *a, **kw: None)

    task_id = 'gen-error-task-1'
    with c.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    # The route re-raises after mark_error, so the exception propagates
    # to Flask's error handler. In TESTING mode, Flask re-raises by
    # default, so we use pytest.raises to catch it.
    with pytest.raises(RuntimeError, match='Unexpected DB failure'):
        c.post('/generate-lessons',
               data=json.dumps({'task_id': task_id}),
               content_type='application/json')

    progress = pt_get_progress(task_id)
    assert progress is not None, "mark_error was not called on generation failure"
    assert progress['mascot_state'] == 'error', (
        f"mascot_state={progress.get('mascot_state')!r}; expected 'error'"
    )
    assert progress.get('error') is True


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_tts_spawn_failure_publishes_mascot_error(
    mock_lesson, mock_quiz, tts_error_client, monkeypatch,
):
    """When the TTS background thread fails to spawn, the route must
    call mark_error so the mascot-error.gif is shown.
    """
    c, app, user = tts_error_client

    mock_lesson.return_value = json.dumps({
        'module_title': 'M1', 'slides': [
            {'type': 'title', 'title': 'T', 'subtitle': ''},
            {'type': 'content', 'heading': 'H', 'bullets': ['a']},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })

    # Make spawn_tts_background_task raise. The route does a local
    # import: `from src.services.tts_worker import spawn_tts_background_task`.
    # Patch at the source module so the local import picks up the mock.
    import src.services.tts_worker as tts_worker_mod
    def boom(*args, **kwargs):
        raise RuntimeError('Thread spawn failed')
    monkeypatch.setattr(tts_worker_mod, 'spawn_tts_background_task', boom)

    task_id = 'tts-spawn-error-task-1'
    with c.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = c.post('/generate-lessons',
                      data=json.dumps({'task_id': task_id}),
                      content_type='application/json')

    assert response.status_code == 200
    progress = pt_get_progress(task_id)
    assert progress is not None, "mark_error was not called on TTS spawn failure"
    assert progress['mascot_state'] == 'error', (
        f"mascot_state={progress.get('mascot_state')!r}; expected 'error'"
    )
    assert progress.get('error') is True


# ── Retake route: TTS cleanup failure no longer crashes ─────────────

@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_retake_tts_cleanup_failure_does_not_crash(
    mock_quiz, mock_lesson, tts_error_client, monkeypatch,
):
    """The retake route must not 500 if delete_module_audio raises
    (e.g. path_id is None). The lesson content was already saved, so
    the route returns success with a warning.
    """
    c, app, user = tts_error_client

    mock_lesson.return_value = json.dumps({
        'module_title': 'M1', 'slides': [
            {'type': 'title', 'title': 'T', 'subtitle': ''},
            {'type': 'content', 'heading': 'H', 'bullets': ['a']},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })

    # Generate a lesson first.
    with c.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']
    c.post('/generate-lessons')

    # Make delete_module_audio raise (simulates path_id=None crash).
    import src.services.tts_service as tts_svc
    def boom(*args, **kwargs):
        raise TypeError('unsupported operand: WindowsPath / NoneType')
    monkeypatch.setattr(tts_svc, 'delete_module_audio', boom)

    # Retake should NOT 500 — the TTS block catches the error.
    response = c.post('/lessons/0/retake',
                      data=json.dumps({'path_id': None}),
                      content_type='application/json')
    assert response.status_code == 200, (
        f"Retake crashed on TTS cleanup failure: {response.status_code} {response.data!r}"
    )
    data = response.get_json()
    assert data is not None
    assert data.get('success') is True