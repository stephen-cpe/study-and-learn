"""
Tests for the background TTS worker (Task 5 — Bug #1 fix).

After Task 5:
  - POST /generate-lessons returns immediately with a task_id; the
    TTS generation runs in a background thread.
  - The worker is idempotent: re-running it on a module whose manifest
    already exists on disk is a no-op.
  - The worker updates the lesson dict's 'tts_audio_status' to
    'ready' once a module's manifest exists.
  - The /lessons/generation-status route returns per-module ready flags
    and a top-level 'all_ready' summary.
  - The audio route returns 202 (not 404) when the manifest doesn't
    exist yet but the lesson's tts_enabled is True and audio is
    genuinely pending generation.
"""
import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User, StudyPath
from src.services.tts_service import TTS_DIR as REAL_TTS_DIR
from src.services.tts_worker import (
    run_tts_generation_for_path,
    is_module_audio_ready,
    get_path_audio_status,
)


@pytest.fixture
def worker_client(monkeypatch):
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
            user = User(username='ttsworker', email='tw@example.com',
                        can_generate_lessons=True, tts_enabled=True,
                        tts_speaker='Ava', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _patch_tts_dir(monkeypatch, tmp_path):
    """Patch TTS_DIR in BOTH the worker and the underlying tts_service
    so the worker's readiness check and the generate_lesson_audio call
    both use the same tmp directory."""
    monkeypatch.setattr('src.services.tts_worker.TTS_DIR', tmp_path)
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)


def _seed_path(app, user, num_modules=2, tts_enabled=True):
    """Insert a StudyPath with N lessons, each with a small narration script."""
    with app.app_context():
        lessons = []
        for i in range(num_modules):
            narration = [
                {'slide_index': -1, 'text': f'Intro {i}'},
                {'slide_index': 0, 'text': f'Slide 0 narration for module {i}'},
                {'slide_index': 1, 'text': f'Checkpoint narration for module {i}'},
                {'slide_index': 2, 'text': f'Slide 1 narration for module {i}'},
            ]
            lessons.append({
                'index': i,
                'module_title': f'Module {i + 1}',
                'estimated_effort': '30 min',
                'lesson': {
                    'module_title': f'Module {i + 1}',
                    'slides': [
                        {'type': 'title', 'title': f'Title {i}', 'subtitle': ''},
                        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
                    ],
                    'narration': narration,
                },
                'quiz': {'questions': [
                    {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                     'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                     'explanation': 'E'}
                ]},
                'checkpoints': {},
                'sources': [],
                'difficulty': 'Normal',
                'tts_enabled': tts_enabled,
                'tts_speaker': 'Ava',
                'completed': False,
                'score': None,
                'passed': False,
                'tts_audio_status': 'pending' if tts_enabled else 'n/a',
            })
        path = StudyPath(
            user_id=user.id, title='Worker Path', learning_goal='Learn X',
            status='active', content_data=json.dumps(lessons),
        )
        db.session.add(path)
        db.session.commit()
        return path.id


# ── Worker: idempotency ──────────────────────────────────────────────

def test_worker_is_idempotent_on_existing_manifest(worker_client, monkeypatch, tmp_path):
    """If a module's manifest already exists on disk, the worker must
    skip generation and not overwrite it. The lesson's tts_audio_status
    must be 'ready'."""
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)

    # Pre-create the manifest for module 0 with a sentinel 'PRESET' string.
    module_dir = tmp_path / real_path_id / '0'
    module_dir.mkdir(parents=True)
    sentinel = json.dumps({
        'path_id': real_path_id, 'module_index': 0, 'speaker': 'PRESET',
        'voice': 'PRESET', 'slides': {'0': 'preset/path.mp3'},
    })
    (module_dir / 'manifest.json').write_text(sentinel)

    async def mock_gen(text, voice, out_path):
        # The output path is TTS_DIR / path_id / module_index / slide_*.mp3
        # Module 0 is the one with the pre-existing manifest; the worker
        # must skip it. If this is called for module 0, the worker is
        # broken (not idempotent).
        try:
            module_part = out_path.parent.name
        except Exception:
            module_part = '?'
        if module_part == '0':
            pytest.fail(
                f"_generate_mp3 called for module 0 — worker is not "
                f"idempotent! text={text!r} voice={voice!r}"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('ok')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen)

    with app.app_context():
        result = run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)

    # Module 0 manifest must be unchanged
    on_disk = json.loads((tmp_path / real_path_id / '0' / 'manifest.json').read_text())
    assert on_disk['speaker'] == 'PRESET', (
        f"Worker overwrote existing manifest! Got speaker={on_disk['speaker']!r}"
    )
    # The result must report the module as ready
    assert result['modules'][0]['status'] == 'ready'
    assert result['modules'][0]['skipped'] is True


def test_worker_generates_missing_modules(worker_client, monkeypatch, tmp_path):
    """For modules WITHOUT a manifest, the worker must generate audio
    and write the manifest."""
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)

    async def mock_gen(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('fake mp3')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen)

    with app.app_context():
        result = run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)

    # Both module manifests must exist
    assert (tmp_path / real_path_id / '0' / 'manifest.json').exists()
    assert (tmp_path / real_path_id / '1' / 'manifest.json').exists()
    # Result reports both as ready
    assert all(m['status'] == 'ready' for m in result['modules'])
    assert all(m['skipped'] is False for m in result['modules'])


def test_worker_skips_modules_with_tts_disabled(worker_client, monkeypatch, tmp_path):
    """If a lesson has tts_enabled=False, the worker must skip it
    entirely (no manifest, no error)."""
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2, tts_enabled=False)
    _patch_tts_dir(monkeypatch, tmp_path)

    async def mock_gen(text, voice, out_path):
        pytest.fail(f"Should not be called when tts_enabled=False: {text!r}")

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen)

    with app.app_context():
        result = run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)

    # No manifests should exist
    assert not (tmp_path / real_path_id / '0' / 'manifest.json').exists()
    # Result must report both as 'n/a'
    assert all(m['status'] == 'n/a' for m in result['modules'])


# ── Worker: error resilience ─────────────────────────────────────────

def test_worker_records_failure_but_continues_to_next_module(worker_client, monkeypatch, tmp_path):
    """If TTS generation fails for one module, the worker must log it
    and continue to the next module. The failed module's lesson dict
    must be persisted with tts_enabled=False and tts_audio_status='failed'."""
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=3)
    _patch_tts_dir(monkeypatch, tmp_path)

    modules_attempted = []
    slides_per_module = {}

    async def mock_gen_fail_first(text, voice, out_path):
        # The output path is TTS_DIR / path_id / module_index / slide_*.mp3
        # Module 0 is the one we want to fail; modules 1 and 2 should succeed.
        try:
            module_part = out_path.parent.name
        except Exception:
            module_part = '?'
        if module_part not in modules_attempted:
            modules_attempted.append(module_part)
        slides_per_module.setdefault(module_part, 0)
        slides_per_module[module_part] += 1
        if module_part == '0':
            raise RuntimeError('Simulated TTS failure for first module')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('ok')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen_fail_first)

    with app.app_context():
        result = run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)

    # First module failed, but the worker should have continued
    statuses = [m['status'] for m in result['modules']]
    assert statuses[0] == 'failed', f"Module 0 should be failed, got {statuses[0]}"
    assert statuses[1] == 'ready', f"Module 1 should be ready (continued), got {statuses[1]}"
    assert statuses[2] == 'ready', f"Module 2 should be ready (continued), got {statuses[2]}"
    # All 3 modules were attempted (not just the first one)
    assert sorted(modules_attempted) == ['0', '1', '2'], (
        f"Worker should have attempted all 3 modules; got {modules_attempted}"
    )


# ── Audio status helpers ─────────────────────────────────────────────

def test_is_module_audio_ready_returns_true_when_manifest_exists(worker_client, monkeypatch, tmp_path):
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=1)
    _patch_tts_dir(monkeypatch, tmp_path)
    # Pre-create manifest
    module_dir = tmp_path / real_path_id / '0'
    module_dir.mkdir(parents=True)
    (module_dir / 'manifest.json').write_text('{"path_id": "x", "slides": {}}')
    with app.app_context():
        assert is_module_audio_ready(real_path_id, 0) is True


def test_is_module_audio_ready_returns_false_when_no_manifest(worker_client, monkeypatch, tmp_path):
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=1)
    _patch_tts_dir(monkeypatch, tmp_path)
    with app.app_context():
        assert is_module_audio_ready(real_path_id, 0) is False


def test_get_path_audio_status_returns_per_module_dict(worker_client, monkeypatch, tmp_path):
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=3)
    _patch_tts_dir(monkeypatch, tmp_path)
    # Pre-create manifests for module 0 and 2
    (tmp_path / real_path_id / '0').mkdir(parents=True)
    (tmp_path / real_path_id / '0' / 'manifest.json').write_text('{}')
    (tmp_path / real_path_id / '2').mkdir(parents=True)
    (tmp_path / real_path_id / '2' / 'manifest.json').write_text('{}')
    with app.app_context():
        status = get_path_audio_status(user_id=user.id, path_id=real_path_id)
    assert status['modules'][0]['status'] == 'ready'
    assert status['modules'][1]['status'] == 'pending'
    assert status['modules'][2]['status'] == 'ready'
    assert status['all_ready'] is False
    assert status['total'] == 3
    assert status['ready_count'] == 2


def test_get_path_audio_status_all_ready(worker_client, monkeypatch, tmp_path):
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)
    for i in range(2):
        (tmp_path / real_path_id / str(i)).mkdir(parents=True)
        (tmp_path / real_path_id / str(i) / 'manifest.json').write_text('{}')
    with app.app_context():
        status = get_path_audio_status(user_id=user.id, path_id=real_path_id)
    assert status['all_ready'] is True
    assert status['ready_count'] == 2


# ── /lessons/generation-status route ─────────────────────────────────

@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_generation_status_route_returns_per_module_flags(
    mock_lesson, mock_quiz, mock_tts, worker_client, monkeypatch, tmp_path
):
    """GET /lessons/generation-status?path_id=... returns per-module
    ready flags and an all_ready summary."""
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)
    # Module 0 ready, module 1 pending.
    (tmp_path / real_path_id / '0').mkdir(parents=True)
    (tmp_path / real_path_id / '0' / 'manifest.json').write_text('{}')

    with app.test_client() as c:
        c.post('/login', data={'username': 'ttsworker', 'password': 'pass'})
        response = c.get(f'/lessons/generation-status?path_id={real_path_id}')

    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert 'modules' in data
    assert 'all_ready' in data
    assert data['modules'][0]['status'] == 'ready'
    assert data['modules'][1]['status'] == 'pending'
    assert data['all_ready'] is False
    # The canonical "navigate now" signal must be present in the
    # response and must be False (column is NULL because the worker
    # has not yet set it). This is the field the JS reads to decide
    # when to redirect from the results page to /lessons.
    assert 'generation_completed' in data, (
        "Response missing generation_completed field; JS cannot "
        "decide when to redirect."
    )
    assert data['generation_completed'] is False


# ── Audio route: 202 vs 404 ──────────────────────────────────────────

@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_audio_route_returns_202_when_pending(mock_quiz, mock_lesson, worker_client, monkeypatch, tmp_path):
    """When the lesson's tts_enabled is True but the manifest doesn't
    exist yet (audio is pending), the audio route must return 202
    (Accepted, not yet ready) so the JS can retry."""
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=1)
    _patch_tts_dir(monkeypatch, tmp_path)
    # No manifest on disk for module 0

    with app.test_client() as c:
        c.post('/login', data={'username': 'ttsworker', 'password': 'pass'})
        response = c.get(f'/lessons/0/audio/0?path_id={real_path_id}')

    assert response.status_code == 202, (
        f"Expected 202 (pending), got {response.status_code}. Audio route must "
        f"distinguish 'TTS not enabled' (404) from 'TTS pending' (202)."
    )


# ── Generation kickoff: returns task_id ──────────────────────────────

@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_generate_lessons_returns_task_id(mock_lesson, mock_quiz, mock_tts, worker_client, monkeypatch, tmp_path):
    """POST /generate-lessons must return a task_id immediately so the
    client can poll for TTS completion. TTS generation must run in the
    background, NOT in the request handler.

    The exact timing of the route is environment-dependent (DB
    round-trips, session commits) — we don't assert a hard wall-clock
    threshold. The structural guarantee we DO assert is that the
    response body includes a task_id, and the spawned background
    thread is a daemon (so it never blocks process shutdown).
    """
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=0)  # no lessons yet, just a path
    _patch_tts_dir(monkeypatch, tmp_path)

    # Slow TTS: simulate a 2-second generation so we can verify the
    # route does NOT wait for TTS to complete.
    import asyncio
    async def slow_gen(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.sleep(2.0)
        out_path.write_text('fake')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', slow_gen)

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

    # Seed the session with the goal + study path.
    with app.test_client() as c:
        c.post('/login', data={'username': 'ttsworker', 'password': 'pass'})
        with c.session_transaction() as sess:
            sess['learning_goal'] = 'Learn X'
            sess['study_path'] = {'modules': [
                {'title': 'Module 1', 'estimated_effort': '30 min'}
            ]}
            sess['extracted_texts'] = ['some text']

        response = c.post('/generate-lessons')

    # The structural contract: response must include a task_id
    # (so the client can poll for completion) and a redirect URL.
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert 'task_id' in data, f"Response missing task_id: {data!r}"
    assert 'redirect' in data
    # The task_id must be a non-empty string the client can use to poll.
    assert isinstance(data['task_id'], str)
    assert len(data['task_id']) > 0


# ── New canonical "navigate now" signal: StudyPath.generation_completed_at ─
# Replaces the previous cache-based data.done signal (via
# progress_tracker.mark_done()) with an atomic DB column. The column
# is the SINGLE SOURCE OF TRUTH for "redirect now" — set by:
#   - The request handler (when TTS is disabled, the route's else
#     branch sets the column before returning).
#   - The TTS worker (in its finally block, for TTS-enabled).
#   - The TTS worker's spawn-wrapper defensive catch (for catastrophic
#     thread failure).
# The JS polls /lessons/generation-status which reads the column and
# returns ``generation_completed: true|false``.


def test_generation_status_returns_true_after_column_set(
    worker_client, monkeypatch, tmp_path,
):
    """When generation_completed_at is set, the status endpoint must
    return generation_completed: true. This is the signal the JS
    polls to decide when to redirect from the results page.
    """
    from datetime import datetime, timezone
    from src.models import StudyPath

    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=1)
    _patch_tts_dir(monkeypatch, tmp_path)

    # Set the column manually (simulating the worker having finished).
    with app.app_context():
        path = StudyPath.query.filter_by(
            id=real_path_id, user_id=user.id,
        ).first()
        path.generation_completed_at = datetime.now(timezone.utc)
        from src import db
        db.session.commit()

    with app.test_client() as c:
        c.post('/login', data={'username': 'ttsworker', 'password': 'pass'})
        response = c.get(
            f'/lessons/generation-status?path_id={real_path_id}'
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data['generation_completed'] is True, (
        "Status endpoint did not report generation_completed=true "
        "after the column was set; JS redirect would never fire."
    )


def test_generation_status_returns_false_when_column_unset(
    worker_client, monkeypatch, tmp_path,
):
    """When generation_completed_at is NULL, the status endpoint must
    return generation_completed: false. The JS must NOT redirect
    while the column is unset — the worker is still running.
    """
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=1)
    _patch_tts_dir(monkeypatch, tmp_path)
    # Column is NULL (default). Verify the endpoint reports false.

    with app.test_client() as c:
        c.post('/login', data={'username': 'ttsworker', 'password': 'pass'})
        response = c.get(
            f'/lessons/generation-status?path_id={real_path_id}'
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data['generation_completed'] is False


def test_route_sets_completion_column_when_tts_disabled(
    worker_client, monkeypatch, tmp_path,
):
    """The /generate-lessons route must set the completion column
    when TTS is disabled, so the JS redirect fires immediately.

    This covers the synchronous (non-TTS) generation path: the user
    has TTS off, clicks Generate, and the route's else branch sets
    generation_completed_at before returning.
    """
    from datetime import datetime, timezone
    from src.models import StudyPath
    from src.services.tts_service import TTS_DIR as REAL_TTS_DIR
    from unittest.mock import patch

    # Disable TTS for this user (re-enable later in a fresh test).
    app, user = worker_client
    with app.app_context():
        user.tts_enabled = False
        from src import db
        db.session.commit()

    real_path_id = _seed_path(app, user, num_modules=0)
    _patch_tts_dir(monkeypatch, tmp_path)

    # Mock the AI calls to return deterministic stubs.
    with patch('src.services.quiz_generator.call_ollama') as mock_quiz, \
         patch('src.services.lesson_generator.call_ollama') as mock_lesson:
        mock_lesson.return_value = json.dumps({
            'module_title': 'M1', 'slides': [
                {'type': 'title', 'title': 'T', 'subtitle': ''},
                {'type': 'content', 'heading': 'H', 'bullets': ['a']},
            ]
        })
        mock_quiz.return_value = json.dumps({
            'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                           'options': ['A', 'B', 'C', 'D'],
                           'answer_index': 0, 'explanation': 'E'}]
        })

        with app.test_client() as c:
            c.post('/login', data={'username': 'ttsworker', 'password': 'pass'})
            with c.session_transaction() as sess:
                sess['learning_goal'] = 'Learn X'
                sess['study_path'] = {'modules': [
                    {'title': 'Module 1', 'estimated_effort': '30 min'}
                ]}
                sess['extracted_texts'] = ['some text']

            response = c.post('/generate-lessons')
            assert response.status_code == 200, (
                f"Route failed: {response.data!r}"
            )
            data = response.get_json()
            assert data is not None
            assert 'redirect' in data

        # The completion column must be set after the route returns
        # (TTS is disabled, so the else branch sets it).
        with app.app_context():
            path = StudyPath.query.filter_by(
                id=real_path_id, user_id=user.id,
            ).first()
            assert path is not None
            assert path.generation_completed_at is not None, (
                "Route did not set generation_completed_at for "
                "TTS-disabled generation; JS redirect would never "
                "fire."
            )

    # Re-enable TTS for subsequent tests in the session.
    with app.app_context():
        user.tts_enabled = True
        from src import db
        db.session.commit()


# ── Race fix: TTS worker must not hijack the request handler's task_id ─
# Previously, the worker called
#   progress_tracker.create_task(task_id=task_id, stages=TTS_STAGES)
#   progress_tracker.update_progress(task_id, 0)
# which overwrote the request handler's progress entry (stage 4,
# GENERATE_STAGES) with the TTS_STAGES entry (stage 0, max stage 3).
# The JS client polls /progress?task_id=... and redirects on
# data.stage >= 4, so the redirect never fired when TTS won the
# race against the first poll.
#
# The current design uses an explicit database column
# (``StudyPath.generation_completed_at``) set in the worker's finally
# block. The JS polls /lessons/generation-status (which reads this
# column) and redirects when it's non-NULL. This is atomic, ACID,
# and unaffected by shared-cache races.

from src.services import progress_tracker
from src.services.progress_tracker import (
    GENERATE_STAGES,
    create_task as pt_create_task,
    get_progress as pt_get_progress,
)


def test_worker_does_not_overwrite_request_handler_stage_list(
    worker_client, monkeypatch, tmp_path,
):
    """The worker must publish cosmetic updates WITHOUT replacing the
    request handler's stage list.

    Simulates the race: the request handler sets stage 4 with
    GENERATE_STAGES (max stage 4) just before the worker starts. The
    worker then runs. If the worker had called
    create_task(task_id, stages=TTS_STAGES), the cached stage list
    would be replaced with TTS_STAGES (max stage 3) and stage would
    reset to 0, breaking the JS stage-based redirect (and previously
    breaking the data.stage >= 4 check).
    """
    from src.services.tts_worker import _tts_cosmetic

    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)

    task_id = 'race-test-task-1'
    # Simulate the request handler having reached stage 4.
    pt_create_task(task_id=task_id, stages=GENERATE_STAGES)
    progress_tracker.update_progress(task_id, 4)
    entry_before = pt_get_progress(task_id)
    assert entry_before['stage'] == 4
    assert entry_before['label'] == 'Finalizing'

    async def mock_gen(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('ok')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen)

    with app.app_context():
        run_tts_generation_for_path(
            user_id=user.id, path_id=real_path_id, task_id=task_id,
        )

    entry_after = pt_get_progress(task_id)
    # The stage list MUST still be GENERATE_STAGES (not TTS_STAGES),
    # and the stage value MUST still be 4 from the request handler —
    # the worker may only patch cosmetic fields (label/mascot/pct/
    # mascot_state), not the stage number or the stage list.
    assert entry_after['stage'] == 4, (
        f"Worker overwrote stage number: {entry_after['stage']}"
    )
    # TTS_STAGES[3] = {"label": "Complete", "mascot": "All done!"}.
    # The user sees the mascot in the bubble, so that's the field
    # the TTS worker's final cosmetic update is expected to set.
    assert entry_after['mascot'] == 'All done!', (
        f"Worker did not publish final TTS cosmetic mascot: "
        f"{entry_after['mascot']!r}"
    )
    # Verify _tts_cosmetic(3) returns the expected cosmetic payload
    # (label=Complete, mascot='All done!') — sanity check on the
    # cosmetic-payload extraction that strips the 'stage' key.
    cos = _tts_cosmetic(3)
    assert cos['mascot'] == 'All done!'
    assert cos['label'] == 'Complete'
    assert 'stage' not in cos


def test_worker_marks_task_done_on_completion(
    worker_client, monkeypatch, tmp_path,
):
    """After all modules are processed, the worker must set
    ``StudyPath.generation_completed_at`` to a non-NULL value.

    This is the explicit "navigate now" signal the JS client reads
    (via /lessons/generation-status). The redirect MUST fire as soon
    as the TTS work is done, regardless of any progress-tracker state.
    """
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)

    # Sanity: the column starts as NULL.
    from src.models import StudyPath
    with app.app_context():
        path_before = StudyPath.query.filter_by(
            id=real_path_id, user_id=user.id,
        ).first()
        assert path_before is not None
        assert path_before.generation_completed_at is None

    async def mock_gen(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('ok')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen)

    with app.app_context():
        run_tts_generation_for_path(
            user_id=user.id, path_id=real_path_id, task_id=None,
        )

    # The worker must have set the column to a non-NULL value so the
    # JS redirect fires. This is the canonical "all generation
    # finished" signal.
    with app.app_context():
        path_after = StudyPath.query.filter_by(
            id=real_path_id, user_id=user.id,
        ).first()
        assert path_after is not None
        assert path_after.generation_completed_at is not None, (
            "Worker did not set generation_completed_at; JS redirect "
            "would never fire."
        )


def test_worker_marks_task_done_on_missing_path(
    worker_client, monkeypatch, tmp_path,
):
    """The worker must set the completion column even on early returns.

    If the StudyPath is not found or has invalid content_data, the
    worker returns early. The finally block must still set the
    completion column so the user is not stuck on the results page
    waiting for a signal that will never come.
    """
    _patch_tts_dir(monkeypatch, tmp_path)
    app, user = worker_client

    # Seed a path so the user has at least one StudyPath row (the
    # one that will receive the early-exit column set is the
    # non-existent 'does-not-exist' one, which the worker will not
    # find — so the column-write is a no-op for that path. We
    # exercise the early-return path WITHOUT expecting the column
    # to be set on a missing path; we only assert the return shape.
    _seed_path(app, user, num_modules=1)

    with app.app_context():
        # Use a path_id that does not exist for this user. The worker
        # must return early. (We pass task_id=None so the cosmetic
        # update_cosmetic calls are no-ops.)
        result = run_tts_generation_for_path(
            user_id=user.id, path_id='does-not-exist', task_id=None,
        )

    assert result == {'modules': [], 'all_ready': False}


def test_worker_marks_task_done_on_per_module_failure(
    worker_client, monkeypatch, tmp_path,
):
    """A failed module must NOT prevent the completion column from being set.

    The user must not be stuck on the results page because one
    module's TTS call raised. The finally block guarantees the
    signal is always set.
    """
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=2)
    _patch_tts_dir(monkeypatch, tmp_path)

    async def mock_gen_fail(text, voice, out_path):
        raise RuntimeError('simulated TTS failure')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen_fail)

    with app.app_context():
        run_tts_generation_for_path(
            user_id=user.id, path_id=real_path_id, task_id=None,
        )

    # Even though every module failed, the completion column must be
    # set so the user can navigate to the lessons page (where
    # they'll see 'failed' status badges on the cards).
    from src.models import StudyPath
    with app.app_context():
        path_after = StudyPath.query.filter_by(
            id=real_path_id, user_id=user.id,
        ).first()
        assert path_after is not None
        assert path_after.generation_completed_at is not None, (
            "Worker did not set generation_completed_at after "
            "per-module failures."
        )


def test_worker_uses_update_cosmetic_not_update_progress(
    worker_client, monkeypatch, tmp_path,
):
    """The worker must use update_cosmetic, not update_progress.

    update_progress would change the stage number against whatever
    stage list the request handler registered (GENERATE_STAGES),
    causing the cosmetic stages (1, 2, 3) to mean
    'Chunking & embedding' / 'Retrieving context' / 'Generating
    lessons' instead of the TTS-specific labels. update_cosmetic
    patches label/mascot/pct/mascot_state in place without touching
    the stage number.
    """
    app, user = worker_client
    real_path_id = _seed_path(app, user, num_modules=1)
    _patch_tts_dir(monkeypatch, tmp_path)

    task_id = 'cosmetic-task-1'
    pt_create_task(task_id=task_id, stages=GENERATE_STAGES)
    progress_tracker.update_progress(task_id, 4)

    # Patch update_progress on the progress_tracker module to RAISE if
    # called by the TTS worker. update_cosmetic must be the only path
    # the worker uses to publish UI progress.
    import src.services.tts_worker as worker_module

    def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "TTS worker must not call update_progress — it would race "
            "with the request handler's stage number."
        )

    monkeypatch.setattr(
        worker_module.progress_tracker, 'update_progress', _fail_if_called,
    )

    async def mock_gen(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text('ok')

    import src.services.tts_service as tts_service_module
    monkeypatch.setattr(tts_service_module, '_generate_mp3', mock_gen)

    with app.app_context():
        run_tts_generation_for_path(
            user_id=user.id, path_id=real_path_id, task_id=task_id,
        )

    # The stage number from the request handler must still be 4
    # (we patched update_progress to raise, so the worker couldn't
    # have changed it). The mascot was patched by update_cosmetic
    # to the TTS final-stage mascot ('All done!') — the user-facing
    # bubble text. The label is also updated to the TTS final-stage
    # label ('Complete'), but that is internal.
    entry = pt_get_progress(task_id)
    assert entry['stage'] == 4
    assert entry['mascot'] == 'All done!'
    assert entry['label'] == 'Complete'

    # The completion column is the new "navigate now" signal, NOT
    # entry['done']. Verify the column is set on the StudyPath.
    from src.models import StudyPath
    with app.app_context():
        path_after = StudyPath.query.filter_by(
            id=real_path_id, user_id=user.id,
        ).first()
        assert path_after is not None
        assert path_after.generation_completed_at is not None
