"""
Tests for Sprint 5 Phase 1.1 — verify Flask-Login, Flask-SQLAlchemy,
Flask-Migrate, and psycopg2 are wired into the app factory without errors.
"""
import pytest
import tempfile
from cachelib import FileSystemCache
from flask import current_app
from src import create_app


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://test:test@localhost:5432/test_db'
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
        yield app_instance


def test_db_extension_initialized(app):
    with app.app_context():
        assert 'sqlalchemy' in current_app.extensions


def test_login_manager_configured(app):
    with app.app_context():
        lm = getattr(current_app, 'login_manager', None)
        assert lm is not None
        assert lm.login_view == 'main.login'
        assert lm.login_message_category == 'error'
        # Dummy user_loader installed so existing non-auth routes still render templates
        assert lm._user_callback is not None


def test_migrate_extension_present(app):
    with app.app_context():
        assert 'migrate' in current_app.extensions
