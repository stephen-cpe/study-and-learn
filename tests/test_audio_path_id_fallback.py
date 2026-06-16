"""
Tests for the lesson_audio path_id fallback.

The audio route /lessons/<i>/audio/<j> and the manifest route
/lessons/<i>/audio/manifest must succeed even when no path_id is
provided in the URL (the JS may navigate without a query string,
e.g. when the user clicks into a lesson from the dashboard which
already filters by active path).

Previously, an empty path_id caused get_lessons(user, path_id='')
to return [] and the route returned 404, even though the user
clearly had lessons with audio files on disk.
"""
import json
import tempfile
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User, StudyPath


@pytest.fixture
def audio_fallback_client(monkeypatch):
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
            user = User(username='audiofallback', email='af@example.com',
                        can_generate_lessons=True, tts_enabled=True,
                        tts_speaker='Ava', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _seed_path_with_lessons_and_audio(app, user, monkeypatch_target, num_modules=1):
    """Insert a StudyPath with N lessons and a real manifest + audio file on disk."""
    with app.app_context():
        lessons = []
        for i in range(num_modules):
            lessons.append({
                'index': i,
                'module_title': f'Module {i + 1}',
                'estimated_effort': '30 min',
                'lesson': {
                    'module_title': f'Module {i + 1}',
                    'slides': [
                        {'type': 'title', 'title': f'Title {i}', 'subtitle': ''},
                        {'type': 'content', 'heading': 'H', 'bullets': ['a', 'b']},
                    ],
                },
                'quiz': {
                    'questions': [
                        {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                         'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                         'explanation': 'E'}
                    ]
                },
                'checkpoints': {},
                'sources': [],
                'difficulty': 'Normal',
                'tts_enabled': True,
                'tts_speaker': 'Ava',
                'completed': False,
                'score': None,
                'passed': False,
            })
        path = StudyPath(
            user_id=user.id, title='Audio Path', learning_goal='Hear audio',
            status='active', content_data=json.dumps(lessons),
        )
        db.session.add(path)
        db.session.commit()
        path_id = path.id
        # Create a real manifest + audio file under the monkeypatched TTS_DIR
        module_dir = monkeypatch_target / path_id / '0'
        module_dir.mkdir(parents=True)
        (module_dir / 'slide_1.mp3').write_bytes(b'fake audio bytes')
        (module_dir / 'manifest.json').write_text(json.dumps({
            'path_id': path_id, 'module_index': 0, 'speaker': 'Ava',
            'voice': 'en-US-AvaNeural',
            'slides': {'0': f'{path_id}/0/slide_1.mp3'},
        }))
        return path_id


def test_audio_route_falls_back_to_active_path_when_path_id_empty(audio_fallback_client, monkeypatch, tmp_path):
    """Regression: GET /lessons/0/audio/0 with NO path_id query string must still
    serve the audio file. The route must derive the path_id from the user's
    most recent active StudyPath."""
    app, user = audio_fallback_client
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)
    real_path_id = _seed_path_with_lessons_and_audio(app, user, tmp_path, num_modules=1)

    with app.test_client() as c:
        c.post('/login', data={'username': 'audiofallback', 'password': 'pass'})
        # NO path_id in the query string
        response = c.get('/lessons/0/audio/0')

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"path_id fallback failed: route should derive from active path."
    )
    assert response.data == b'fake audio bytes'


def test_audio_manifest_falls_back_to_active_path_when_path_id_empty(audio_fallback_client, monkeypatch, tmp_path):
    """Regression: GET /lessons/0/audio/manifest with NO path_id query string
    must still return the manifest JSON. The route must derive the path_id
    from the user's most recent active StudyPath."""
    app, user = audio_fallback_client
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)
    real_path_id = _seed_path_with_lessons_and_audio(app, user, tmp_path, num_modules=1)

    with app.test_client() as c:
        c.post('/login', data={'username': 'audiofallback', 'password': 'pass'})
        response = c.get('/lessons/0/audio/manifest')

    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get('path_id') == real_path_id
    assert '0' in data.get('slides', {})


def test_audio_route_with_explicit_path_id_still_works(audio_fallback_client, monkeypatch, tmp_path):
    """Sanity: explicit path_id in query string must still take precedence over fallback."""
    app, user = audio_fallback_client
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)
    real_path_id = _seed_path_with_lessons_and_audio(app, user, tmp_path, num_modules=1)

    with app.test_client() as c:
        c.post('/login', data={'username': 'audiofallback', 'password': 'pass'})
        response = c.get(f'/lessons/0/audio/0?path_id={real_path_id}')

    assert response.status_code == 200
    assert response.data == b'fake audio bytes'


def test_audio_route_returns_404_when_no_active_path(audio_fallback_client, monkeypatch, tmp_path):
    """Sanity: when the user has no active path AND no path_id in URL, the route
    must return 404 (no implicit creation of a fake path)."""
    app, user = audio_fallback_client
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)
    # No seeding — user has no active paths.

    with app.test_client() as c:
        c.post('/login', data={'username': 'audiofallback', 'password': 'pass'})
        response = c.get('/lessons/0/audio/0')

    assert response.status_code == 404


def test_audio_route_uses_most_recent_active_path(audio_fallback_client, monkeypatch, tmp_path):
    """Sanity: when a user has multiple active paths, the audio route must
    use the most recently created one (matching get_most_recent_active_path)."""
    app, user = audio_fallback_client
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)

    with app.app_context():
        # Create two paths: one older, one newer.
        lessons = [{
            'index': 0, 'module_title': 'M', 'estimated_effort': '1h',
            'lesson': {'module_title': 'M', 'slides': [{'type': 'title', 'title': 'T', 'subtitle': ''}]},
            'quiz': {'questions': []}, 'checkpoints': {}, 'sources': [],
            'difficulty': 'Normal', 'tts_enabled': True, 'tts_speaker': 'Ava',
            'completed': False, 'score': None, 'passed': False,
        }]
        from datetime import datetime, timezone, timedelta
        older = StudyPath(
            user_id=user.id, title='Older', learning_goal='Old',
            status='active', content_data=json.dumps(lessons),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.session.add(older)
        db.session.commit()
        older_id = older.id
        newer = StudyPath(
            user_id=user.id, title='Newer', learning_goal='New',
            status='active', content_data=json.dumps(lessons),
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(newer)
        db.session.commit()
        newer_id = newer.id

        # Audio files exist only under the newer path's directory.
        module_dir = tmp_path / newer_id / '0'
        module_dir.mkdir(parents=True)
        (module_dir / 'slide_1.mp3').write_bytes(b'newer audio')
        (module_dir / 'manifest.json').write_text(json.dumps({
            'path_id': newer_id, 'module_index': 0, 'speaker': 'Ava',
            'voice': 'en-US-AvaNeural',
            'slides': {'0': f'{newer_id}/0/slide_1.mp3'},
        }))
        # Also create one for the older path (so we can verify the route picks newer).
        older_dir = tmp_path / older_id / '0'
        older_dir.mkdir(parents=True)
        (older_dir / 'slide_1.mp3').write_bytes(b'older audio')
        (older_dir / 'manifest.json').write_text(json.dumps({
            'path_id': older_id, 'module_index': 0, 'speaker': 'Ava',
            'voice': 'en-US-AvaNeural',
            'slides': {'0': f'{older_id}/0/slide_1.mp3'},
        }))

    with app.test_client() as c:
        c.post('/login', data={'username': 'audiofallback', 'password': 'pass'})
        response = c.get('/lessons/0/audio/0')

    assert response.status_code == 200
    assert response.data == b'newer audio'
