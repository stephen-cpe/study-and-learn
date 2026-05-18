"""
Tests for Sprint 5 Phase 2.1 — StudyPath & LessonProgress models + 3-lesson cap.

The fixture below overrides SQLALCHEMY_DATABASE_URI to an in-memory SQLite DB
so model unit tests run quickly and in isolation. The real DATABASE_URL is still
set first so the app factory's PostgreSQL validation passes at startup.
"""
import pytest
import tempfile
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User, StudyPath, LessonProgress


@pytest.fixture
def app(monkeypatch):
    # App factory requires a valid PostgreSQL URL to pass validation;
    # we override to SQLite for isolated unit tests.
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
        # Override to SQLite for isolated model unit tests only
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        # Remove sqlalchemy extension so init_app can re-register with the new URI
        app_instance.extensions.pop('sqlalchemy', None)
        # Re-init to build an SQLite engine for this app
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            yield app_instance
            db.session.remove()
            db.drop_all()


def test_study_path_creation_and_user_relationship(app):
    """Creating a StudyPath links it to a User via relationship."""
    with app.app_context():
        user = User(username='learner', email='learner@example.com')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        path = StudyPath(
            user_id=user.id,
            title='Intro to ML',
            learning_goal='Learn machine learning basics',
        )
        db.session.add(path)
        db.session.commit()

        assert path.id is not None
        assert path.user_id == user.id
        assert path.status == 'active'
        assert path.title == 'Intro to ML'
        assert path.user == user
        assert StudyPath.query.filter_by(user_id=user.id).count() == 1


def test_lesson_progress_tracking(app):
    """LessonProgress records score, passed, and completed state."""
    with app.app_context():
        user = User(username='student', email='student@example.com')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        path = StudyPath(
            user_id=user.id,
            title='Physics 101',
            learning_goal='Learn basic physics',
        )
        db.session.add(path)
        db.session.commit()

        prog = LessonProgress(
            study_path_id=path.id,
            module_index=0,
            score=85,
            passed=True,
            completed=True,
        )
        db.session.add(prog)
        db.session.commit()

        assert prog.study_path == path
        assert prog.score == 85
        assert prog.passed is True
        assert prog.completed is True
        assert LessonProgress.query.filter_by(study_path_id=path.id).count() == 1


def test_three_lesson_cap_blocks_new_lessons(app):
    """A user cannot start more than 3 active lessons simultaneously."""
    with app.app_context():
        user = User(username='captest', email='cap@example.com')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        for i in range(3):
            path = StudyPath(
                user_id=user.id,
                title=f'Course {i}',
                learning_goal=f'Goal {i}',
            )
            db.session.add(path)
        db.session.commit()

        assert user.active_lesson_count == 3
        assert user.can_start_new_lesson() is False


def test_completing_lesson_frees_up_cap(app):
    """Marking a StudyPath as completed frees a slot for a new lesson."""
    with app.app_context():
        user = User(username='freetest', email='free@example.com')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        for i in range(3):
            path = StudyPath(
                user_id=user.id,
                title=f'Course {i}',
                learning_goal=f'Goal {i}',
            )
            db.session.add(path)
        db.session.commit()

        assert user.can_start_new_lesson() is False

        # Mark the first path as completed
        path = StudyPath.query.filter_by(user_id=user.id).first()
        path.status = 'completed'
        db.session.commit()

        assert user.active_lesson_count == 2
        assert user.can_start_new_lesson() is True
