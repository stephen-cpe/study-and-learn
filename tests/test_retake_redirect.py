"""
Tests for the retake redirect UX (Task 3).

After a successful retake, the server must:
  1. Reset the lesson's deck_position to 0 so the user starts from slide 0.
  2. Return a JSON body that includes a 'redirect' URL the JS can navigate
     to (instead of a blind window.location.reload() that leaves the user
     on the results slide with stale UI).

The retake route must continue to:
  - Accept path_id from query string OR JSON body (Task 1 contract).
  - Return 200 with success=True on a valid retake.
  - Persist the new artifacts (quiz, checkpoints, lesson slides) so the
    next page load shows the regenerated content.
"""
import json
import tempfile
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User, StudyPath


@pytest.fixture
def retake_client(monkeypatch):
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
            user = User(username='retaketester', email='rt@example.com',
                        can_generate_lessons=True, tts_enabled=True,
                        tts_speaker='Ava', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _seed_path_with_failing_user(app, user, module_index=0, num_modules=2,
                                 deck_position=5):
    """Seed a StudyPath where module_index has a failing grade and the user
    has navigated to slide 5 (mid-deck). The retake must reset deck_position
    and return a redirect URL pointing to the deck for this module."""
    with app.app_context():
        lessons = []
        for i in range(num_modules):
            is_failed = (i == module_index)
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
                'completed': True,
                'score': 40 if is_failed else 100,
                'passed': False if is_failed else True,
                'deck_position': deck_position if is_failed else 0,
            })
        path = StudyPath(
            user_id=user.id, title='Retake Path', learning_goal='Learn X',
            status='active', content_data=json.dumps(lessons),
        )
        db.session.add(path)
        db.session.commit()
        return path.id


@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_retake_returns_redirect_url_in_response(mock_lesson, mock_quiz, mock_tts, retake_client):
    """Regression: server must include a 'redirect' URL in the response so the
    client can navigate to the deck for this module with the regenerated content."""
    app, user = retake_client
    real_path_id = _seed_path_with_failing_user(app, user, module_index=0, num_modules=2)
    mock_lesson.return_value = json.dumps({
        'module_title': 'Module 1', 'slides': [
            {'type': 'title', 'title': 'Fresh Title', 'subtitle': 'Fresh subtitle'},
            {'type': 'content', 'heading': 'Fresh Heading', 'bullets': ['a', 'b']},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q_fresh', 'type': 'mcq', 'prompt': 'Fresh?',
                       'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                       'explanation': 'E'}]
    })
    mock_tts.return_value = {}

    with app.test_client() as c:
        c.post('/login', data={'username': 'retaketester', 'password': 'pass'})
        response = c.post(
            '/lessons/0/retake',
            data=json.dumps({'path_id': real_path_id}),
            content_type='application/json',
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get('success') is True
    # The new contract: include a 'redirect' URL.
    assert 'redirect' in data, f"Response missing 'redirect' key: {data!r}"
    redirect_url = data['redirect']
    assert '/lessons/0' in redirect_url, (
        f"Redirect should target the retaken module's deck, got {redirect_url!r}"
    )
    assert f'path_id={real_path_id}' in redirect_url, (
        f"Redirect must include the path_id so the deck loads the right lessons, "
        f"got {redirect_url!r}"
    )


@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_retake_resets_deck_position_to_zero(mock_lesson, mock_quiz, mock_tts, retake_client):
    """Regression: after retake, the user's saved deck_position must be reset to 0
    so they restart from the beginning instead of being dropped mid-deck with stale
    state."""
    app, user = retake_client
    real_path_id = _seed_path_with_failing_user(
        app, user, module_index=0, num_modules=2, deck_position=7
    )
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
    mock_tts.return_value = {}

    with app.test_client() as c:
        c.post('/login', data={'username': 'retaketester', 'password': 'pass'})
        c.post(
            '/lessons/0/retake',
            data=json.dumps({'path_id': real_path_id}),
            content_type='application/json',
        )

    # Re-fetch the lesson and check deck_position is now 0.
    with app.app_context():
        from src.repositories.lesson_repo import get_lessons
        path = StudyPath.query.filter_by(id=real_path_id).first()
        lessons = get_lessons(user, path_id=real_path_id)
        assert lessons[0].get('deck_position', 0) == 0, (
            f"Expected deck_position reset to 0, got {lessons[0].get('deck_position')!r}"
        )
        # Sanity: score/passed/completed are also reset.
        assert lessons[0]['score'] is None
        assert lessons[0]['passed'] is False
        assert lessons[0]['completed'] is False


@patch('src.services.tts_service.generate_lesson_audio')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.lesson_generator.call_ollama')
def test_retake_persists_fresh_quiz(mock_lesson, mock_quiz, mock_tts, retake_client):
    """Sanity: the regenerated quiz must be persisted to the DB so the next
    page load (via the redirect) shows the fresh questions.

    Note: retake reuses the existing slides (per orchestrator design — see
    build_module_artifacts existing_slides branch) and only regenerates the
    quiz + checkpoints. Slides are not part of retake scope.
    """
    app, user = retake_client
    real_path_id = _seed_path_with_failing_user(app, user, module_index=0, num_modules=2)
    # The mock_lesson response is irrelevant — retake reuses existing_slides
    # and never calls the lesson generator. But mock it to avoid surprises.
    mock_lesson.return_value = json.dumps({
        'module_title': 'Module 1', 'slides': [
            {'type': 'title', 'title': 'T', 'subtitle': ''},
        ]
    })
    mock_quiz.return_value = json.dumps({
        'questions': [{'id': 'q_NEW', 'type': 'mcq', 'prompt': 'NEW?',
                       'options': ['W', 'X', 'Y', 'Z'], 'answer_index': 2,
                       'explanation': 'Because'}]
    })
    mock_tts.return_value = {}

    with app.test_client() as c:
        c.post('/login', data={'username': 'retaketester', 'password': 'pass'})
        c.post(
            '/lessons/0/retake',
            data=json.dumps({'path_id': real_path_id}),
            content_type='application/json',
        )

    with app.app_context():
        from src.repositories.lesson_repo import get_lessons
        lessons = get_lessons(user, path_id=real_path_id)
        assert lessons[0]['quiz']['questions'][0]['id'] == 'q_NEW', (
            f"Expected fresh quiz question id 'q_NEW', got "
            f"{lessons[0]['quiz']['questions'][0].get('id')!r}"
        )
