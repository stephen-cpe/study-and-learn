"""
Tests for Sprint 5 Phase 1.2 — User SQLAlchemy model.

The fixture below overrides SQLALCHEMY_DATABASE_URI to an in-memory SQLite DB
so model unit tests run quickly and in isolation. The real DATABASE_URL is still
set first so the app factory's PostgreSQL validation passes at startup.
"""
import pytest
import tempfile
from cachelib import FileSystemCache
from sqlalchemy.exc import IntegrityError
from src import create_app, db
from src.models import User


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


def test_user_password_hashing(app):
    with app.app_context():
        user = User(username='alice', email='alice@example.com')
        user.set_password('secret123')
        assert user.password_hash != 'secret123'
        assert user.password_hash is not None


def test_user_password_verification(app):
    with app.app_context():
        user = User(username='bob', email='bob@example.com')
        user.set_password('mypassword')
        assert user.check_password('mypassword') is True
        assert user.check_password('wrongpassword') is False


def test_unique_username_constraint(app):
    with app.app_context():
        u1 = User(username='dup', email='a@example.com')
        u1.set_password('pass')
        u2 = User(username='dup', email='b@example.com')
        u2.set_password('pass')
        db.session.add(u1)
        db.session.commit()
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_unique_email_constraint(app):
    with app.app_context():
        u1 = User(username='user1', email='same@example.com')
        u1.set_password('pass')
        u2 = User(username='user2', email='same@example.com')
        u2.set_password('pass')
        db.session.add(u1)
        db.session.commit()
        db.session.add(u2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_user_repr(app):
    with app.app_context():
        user = User(username='charlie', email='charlie@example.com', is_admin=False)
        user.set_password('x')
        assert repr(user) == "<User charlie (charlie@example.com) admin=False>"


def test_user_mixin_methods(app):
    with app.app_context():
        user = User(username='demo', email='demo@example.com')
        user.set_password('demo')
        assert user.is_authenticated is True
        assert user.is_active is True
        assert user.is_anonymous is not True
        assert user.get_id() is not None
