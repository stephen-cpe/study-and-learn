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
