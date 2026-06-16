"""
Tests for path_id transport contract.

The JS client may send path_id either as a query-string parameter
(current convention) or in the JSON request body (older retake path).
Every lessons route that consumes path_id must accept it from BOTH
locations. This prevents the 'unsupported operand types for / :
WindowsPath and NoneType' 500 from /lessons/<i>/retake that happens
when path_id is sent only in the body.
"""
import json
import tempfile
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User, StudyPath


@pytest.fixture
def path_id_client(monkeypatch):
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
            user = User(username='pathtester', email='path@example.com',
                        can_generate_lessons=True, tts_enabled=True,
                        tts_speaker='Ava', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _seed_lessons(app, user, path_id, num_modules=2):
    """Insert a StudyPath with N lessons so the routes have something to act on."""
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
            user_id=user.id, title='Test Path', learning_goal='Learn X',
            status='active', content_data=json.dumps(lessons),
        )
        db.session.add(path)
        db.session.commit()
        return path.id


@patch('src.services.tts_service.delete_module_audio')
@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_retake_accepts_path_id_from_json_body(mock_lesson, mock_quiz, mock_tts_gen, mock_tts_del, path_id_client):
    """Regression: /retake used to read path_id only from query string and crashed with
    TypeError when JS sent it in the JSON body. Server must accept it from the body."""
    app, user = path_id_client
    real_path_id = _seed_lessons(app, user, None, num_modules=2)
    mock_lesson.return_value = json.dumps({
        'module_title': 'Module 1', 'slides': [
            {'type': 'title', 'title': 'T', 'subtitle': ''},
            {'type': 'content', 'heading': 'H', 'bullets': ['a', 'b']},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })

    with app.test_client() as c:
        c.post('/login', data={'username': 'pathtester', 'password': 'pass'})
        # JS sends path_id in the JSON body (no query string)
        response = c.post(
            f'/lessons/0/retake',
            data=json.dumps({'path_id': real_path_id}),
            content_type='application/json',
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.data!r}"
    data = response.get_json()
    assert data is not None
    assert data.get('success') is True
    # delete_module_audio must have been called with the real path_id, NOT None
    if mock_tts_del.called:
        args, _ = mock_tts_del.call_args
        assert args[0] == real_path_id, f"Expected path_id={real_path_id}, got {args[0]!r}"


@patch('src.services.tts_service.delete_module_audio')
@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_retake_accepts_path_id_from_query_string(mock_lesson, mock_quiz, mock_tts_gen, mock_tts_del, path_id_client):
    """Sanity: the original query-string transport must still work."""
    app, user = path_id_client
    real_path_id = _seed_lessons(app, user, None, num_modules=2)
    mock_lesson.return_value = json.dumps({
        'module_title': 'Module 1', 'slides': [
            {'type': 'title', 'title': 'T', 'subtitle': ''},
            {'type': 'content', 'heading': 'H', 'bullets': ['a', 'b']},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })

    with app.test_client() as c:
        c.post('/login', data={'username': 'pathtester', 'password': 'pass'})
        response = c.post(
            f'/lessons/0/retake?path_id={real_path_id}',
            data='{}',
            content_type='application/json',
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data.get('success') is True


@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_grade_accepts_path_id_from_query_string(mock_lesson, mock_quiz, path_id_client):
    """Sanity: /grade must continue to accept path_id from query string."""
    app, user = path_id_client
    real_path_id = _seed_lessons(app, user, None, num_modules=1)
    with app.test_client() as c:
        c.post('/login', data={'username': 'pathtester', 'password': 'pass'})
        response = c.post(
            f'/lessons/0/grade?path_id={real_path_id}',
            data=json.dumps({
                'answers': [0],
                'checkpoint_answers': {},
            }),
            content_type='application/json',
        )
    assert response.status_code == 200
    data = response.get_json()
    assert 'score' in data


def test_save_position_accepts_path_id_from_query_string(path_id_client):
    """Sanity: /save-position must accept path_id from query string."""
    app, user = path_id_client
    real_path_id = _seed_lessons(app, user, None, num_modules=1)
    with app.test_client() as c:
        c.post('/login', data={'username': 'pathtester', 'password': 'pass'})
        response = c.post(
            f'/lessons/0/save-position?path_id={real_path_id}',
            data=json.dumps({'slide_index': 2}),
            content_type='application/json',
        )
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('ok') is True


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.tts_service.generate_lesson_audio')
def test_audio_route_accepts_path_id_from_query_string(mock_tts, mock_quiz, mock_lesson, path_id_client, monkeypatch, tmp_path):
    """Sanity: /audio/<i> must accept path_id from query string and return 200 when
    a real manifest exists on disk."""
    app, user = path_id_client
    real_path_id = _seed_lessons(app, user, None, num_modules=1)
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)
    # Create a real manifest + audio file under tmp_path / real_path_id / 0.
    # TTS service writes slide_{si+1}.mp3 for entry slide_index=si.
    # Manifest keys are str(si).
    module_dir = tmp_path / real_path_id / '0'
    module_dir.mkdir(parents=True)
    (module_dir / 'slide_1.mp3').write_bytes(b'fake mp3')
    (module_dir / 'manifest.json').write_text(json.dumps({
        'path_id': real_path_id, 'module_index': 0, 'speaker': 'Ava',
        'voice': 'en-US-AvaNeural', 'slides': {'0': f'{real_path_id}/0/slide_1.mp3'},
    }))
    mock_tts.return_value = {}
    mock_lesson.return_value = json.dumps({
        'module_title': 'Module 1', 'slides': [
            {'type': 'title', 'title': 'T', 'subtitle': ''},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })
    with app.test_client() as c:
        c.post('/login', data={'username': 'pathtester', 'password': 'pass'})
        response = c.get(f'/lessons/0/audio/0?path_id={real_path_id}')
    assert response.status_code == 200
    assert response.data == b'fake mp3'


def test_lesson_audio_manifest_accepts_path_id_from_query_string(path_id_client):
    """Sanity: /lessons/<i>/audio/manifest must accept path_id from query string."""
    app, user = path_id_client
    real_path_id = _seed_lessons(app, user, None, num_modules=1)
    with app.test_client() as c:
        c.post('/login', data={'username': 'pathtester', 'password': 'pass'})
        response = c.get(f'/lessons/0/audio/manifest?path_id={real_path_id}')
    assert response.status_code == 200
    data = response.get_json()
    # No manifest on disk, so empty dict is expected
    assert data == {}
