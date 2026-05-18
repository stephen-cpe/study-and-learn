"""
Tests for Sprint 5 Phase 2.2 — DB-backed LessonRepository.

Uses the SQLite in-memory fixture pattern established in test_lesson_models.py.
"""
import json
import pytest
import tempfile
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User, StudyPath, LessonProgress
from src.repositories.lesson_repo import get_lessons, save_lessons


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        app_instance = create_app()
        app_instance.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(
                cache_dir=temp_dir, threshold=500, mode=0o700
            ),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app_instance)
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app_instance.extensions.pop('sqlalchemy', None)
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            yield app_instance
            db.session.remove()
            db.drop_all()


def _make_user(app):
    with app.app_context():
        user = User(username='learner', email='learner@example.com')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()
        return user.id


def _make_sample_lessons():
    return [
        {
            'index': 0,
            'module_title': 'Intro to ML',
            'estimated_effort': '2 hours',
            'lesson': {'module_title': 'Intro to ML', 'slides': [
                {'type': 'title', 'title': 'Welcome', 'subtitle': 'ML Basics'}
            ]},
            'quiz': {'questions': [
                {'id': 'q1', 'type': 'mcq', 'prompt': 'What is ML?',
                 'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                 'explanation': 'ML is AI'}
            ]},
            'checkpoints': {},
            'completed': False,
            'score': None,
            'passed': False,
        },
        {
            'index': 1,
            'module_title': 'Neural Networks',
            'estimated_effort': '3 hours',
            'lesson': {'module_title': 'Neural Networks', 'slides': [
                {'type': 'content', 'heading': 'Overview',
                 'bullets': ['Point 1', 'Point 2'], 'notes': ''}
            ]},
            'quiz': {'questions': [
                {'id': 'q2', 'type': 'true_false', 'prompt': 'T/F?',
                 'answer': True, 'explanation': 'E'}
            ]},
            'checkpoints': {},
            'completed': False,
            'score': None,
            'passed': False,
        },
    ]


def test_get_lessons_returns_empty_for_unauthenticated(app):
    with app.app_context():
        result = get_lessons()
        assert result == []


def test_db_lesson_roundtrip(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        path = StudyPath(
            user_id=user.id, title='Test Path',
            learning_goal='Learn ML basics'
        )
        db.session.add(path)
        db.session.commit()

        lessons = _make_sample_lessons()
        save_lessons(lessons, user)

        loaded = get_lessons(user)
        assert len(loaded) == 2
        assert loaded[0]['module_title'] == 'Intro to ML'
        assert loaded[1]['module_title'] == 'Neural Networks'
        assert loaded[0]['lesson']['slides'][0]['title'] == 'Welcome'
        assert loaded[0]['quiz']['questions'][0]['prompt'] == 'What is ML?'


def test_lessons_persisted_as_json_in_content_data(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        path = StudyPath(
            user_id=user.id, title='JSON Test',
            learning_goal='Learn'
        )
        db.session.add(path)
        db.session.commit()

        lessons = _make_sample_lessons()
        save_lessons(lessons, user)

        path_refreshed = StudyPath.query.filter_by(user_id=user.id, status='active').first()
        assert path_refreshed is not None
        assert path_refreshed.content_data is not None

        parsed = json.loads(path_refreshed.content_data)
        assert len(parsed) == 2
        assert parsed[0]['module_title'] == 'Intro to ML'


def test_save_lessons_creates_lesson_progress_rows(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        path = StudyPath(
            user_id=user.id, title='Prog Test',
            learning_goal='Learn'
        )
        db.session.add(path)
        db.session.commit()

        lessons = _make_sample_lessons()
        save_lessons(lessons, user)

        rows = LessonProgress.query.filter_by(study_path_id=path.id).all()
        assert len(rows) == 2
        indices = sorted(r.module_index for r in rows)
        assert indices == [0, 1]


def test_user_isolation(app):
    with app.app_context():
        u_a = User(username='alice', email='alice@test.com')
        u_a.set_password('pass')
        u_b = User(username='bob', email='bob@test.com')
        u_b.set_password('pass')
        db.session.add_all([u_a, u_b])
        db.session.commit()

        path_a = StudyPath(
            user_id=u_a.id, title='Alice Path',
            learning_goal='Alice goal'
        )
        path_b = StudyPath(
            user_id=u_b.id, title='Bob Path',
            learning_goal='Bob goal'
        )
        db.session.add_all([path_a, path_b])
        db.session.commit()

        lessons_a = [
            {'index': 0, 'module_title': 'Alice Module', 'estimated_effort': '1h',
             'lesson': {'slides': []}, 'quiz': {'questions': []},
             'checkpoints': {}, 'completed': False, 'score': None, 'passed': False}
        ]
        lessons_b = [
            {'index': 0, 'module_title': 'Bob Module', 'estimated_effort': '1h',
             'lesson': {'slides': []}, 'quiz': {'questions': []},
             'checkpoints': {}, 'completed': False, 'score': None, 'passed': False}
        ]

        save_lessons(lessons_a, u_a)
        save_lessons(lessons_b, u_b)

        loaded_a = get_lessons(u_a)
        loaded_b = get_lessons(u_b)

        assert len(loaded_a) == 1
        assert len(loaded_b) == 1
        assert loaded_a[0]['module_title'] == 'Alice Module'
        assert loaded_b[0]['module_title'] == 'Bob Module'


def test_progress_state_persistence(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        path = StudyPath(
            user_id=user.id, title='State Test',
            learning_goal='Learn'
        )
        db.session.add(path)
        db.session.commit()

        lessons = _make_sample_lessons()
        lessons[0]['score'] = 85
        lessons[0]['passed'] = True
        lessons[0]['completed'] = True

        save_lessons(lessons, user)

        loaded = get_lessons(user)
        assert loaded[0]['score'] == 85
        assert loaded[0]['passed'] is True
        assert loaded[0]['completed'] is True

        assert loaded[1]['score'] is None
        assert loaded[1]['passed'] is False
        assert loaded[1]['completed'] is False


def test_progress_survives_across_save_get_cycles(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        path = StudyPath(
            user_id=user.id, title='Cycle Test',
            learning_goal='Learn'
        )
        db.session.add(path)
        db.session.commit()

        lessons = _make_sample_lessons()
        save_lessons(lessons, user)

        loaded_1 = get_lessons(user)
        loaded_1[0]['score'] = 90
        loaded_1[0]['passed'] = True
        loaded_1[0]['completed'] = True
        loaded_1[1]['score'] = 60
        loaded_1[1]['passed'] = False
        loaded_1[1]['completed'] = True
        save_lessons(loaded_1, user)

        loaded_2 = get_lessons(user)
        assert loaded_2[0]['score'] == 90
        assert loaded_2[0]['passed'] is True
        assert loaded_2[0]['completed'] is True
        assert loaded_2[1]['score'] == 60
        assert loaded_2[1]['passed'] is False
        assert loaded_2[1]['completed'] is True

        rows = LessonProgress.query.filter_by(study_path_id=path.id).all()
        assert len(rows) == 2

        loaded_2[0]['score'] = None
        loaded_2[0]['passed'] = False
        loaded_2[0]['completed'] = False
        save_lessons(loaded_2, user)

        loaded_3 = get_lessons(user)
        assert loaded_3[0]['score'] is None
        assert loaded_3[0]['passed'] is False
        assert loaded_3[0]['completed'] is False


def test_save_lessons_creates_path_when_none_exists(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        existing = StudyPath.query.filter_by(user_id=user.id, status='active').first()
        assert existing is None

        lessons = _make_sample_lessons()
        save_lessons(lessons, user)

        new_path = StudyPath.query.filter_by(user_id=user.id, status='active').first()
        assert new_path is not None
        assert new_path.content_data is not None

        loaded = get_lessons(user)
        assert len(loaded) == 2


def test_save_lessons_removes_stale_progress_rows(app):
    with app.app_context():
        user_id = _make_user(app)
        user = db.session.get(User, user_id)

        path = StudyPath(
            user_id=user.id, title='Stale Test',
            learning_goal='Learn'
        )
        db.session.add(path)
        db.session.commit()

        lessons_full = _make_sample_lessons()
        save_lessons(lessons_full, user)

        rows_before = LessonProgress.query.filter_by(study_path_id=path.id).all()
        assert len(rows_before) == 2

        lessons_single = _make_sample_lessons()[:1]
        save_lessons(lessons_single, user)

        rows_after = LessonProgress.query.filter_by(study_path_id=path.id).all()
        assert len(rows_after) == 1
        assert rows_after[0].module_index == 0

        loaded = get_lessons(user)
        assert len(loaded) == 1
