"""
Tests for Sprint 5 Phase 2.3 — Learner Dashboard + Cancel/Abandon + 3-Lesson Cap UI.

Uses the SQLite in-memory fixture pattern established in test_integration.py.
"""
import io
import tempfile
import pytest
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User, StudyPath, LessonProgress


@pytest.fixture
def client(monkeypatch):
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
            user = User(username='dashuser', email='dash@example.com')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'dashuser', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


def _make_active_path(client, title='Intro to ML', goal='Learn ML basics'):
    user = User.query.filter_by(username='dashuser').first()
    path = StudyPath(
        user_id=user.id, title=title,
        learning_goal=goal, status='active',
    )
    db.session.add(path)
    db.session.commit()

    for i in range(2):
        lp = LessonProgress(
            study_path_id=path.id, module_index=i,
            score=85, passed=True, completed=True,
        )
        db.session.add(lp)
    db.session.commit()
    return path


def _make_path_no_progress(client, title='Empty Path', goal='Empty'):
    user = User.query.filter_by(username='dashuser').first()
    path = StudyPath(
        user_id=user.id, title=title,
        learning_goal=goal, status='active',
    )
    db.session.add(path)
    db.session.commit()
    return path


def test_dashboard_renders_active_paths(client):
    _make_active_path(client)

    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'My Learning Dashboard' in rv.data
    assert b'Intro to ML' in rv.data
    assert b'100%' in rv.data
    assert b'View Lessons' in rv.data
    assert b'Cancel / Abandon' in rv.data


def test_cancel_path_updates_status(client):
    path = _make_active_path(client)

    rv = client.post(f'/study-path/{path.id}/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'has been cancelled' in rv.data
    assert b'My Learning Dashboard' in rv.data

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'cancelled'


def test_cap_warning_banner_shows_at_limit(client):
    user = User.query.filter_by(username='dashuser').first()
    for i in range(3):
        path = StudyPath(
            user_id=user.id, title=f'Course {i}',
            learning_goal=f'Goal {i}', status='active',
        )
        db.session.add(path)
    db.session.commit()

    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'Lesson Cap Reached' in rv.data
    assert b'maximum of 3 active lessons' in rv.data.lower()


def test_empty_dashboard_shows_start_prompt(client):
    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'No active lessons' in rv.data
    assert b'Start New Lesson' in rv.data
    assert b'Upload materials' in rv.data


def test_cancel_nonexistent_path_flashes_error(client):
    rv = client.post('/study-path/nonexistent-id/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Study path not found' in rv.data


def test_cannot_cancel_other_users_path(client):
    other = User(username='other', email='other@example.com')
    other.set_password('pass')
    db.session.add(other)
    db.session.commit()
    path = StudyPath(
        user_id=other.id, title='Other Path',
        learning_goal='Secret', status='active',
    )
    db.session.add(path)
    db.session.commit()

    rv = client.post(f'/study-path/{path.id}/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Study path not found' in rv.data

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'active'


def test_reset_preserves_paths_with_lessons(client):
    path = _make_active_path(client)

    rv = client.get('/reset', follow_redirects=True)
    assert rv.status_code == 200

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'active', (
        "Paths with generated lessons should remain active after reset"
    )


def test_reset_cancels_paths_without_lessons(client):
    path = _make_path_no_progress(client)

    rv = client.get('/reset', follow_redirects=True)
    assert rv.status_code == 200

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'cancelled', (
        "Paths with zero LessonProgress rows should be cancelled on reset"
    )
