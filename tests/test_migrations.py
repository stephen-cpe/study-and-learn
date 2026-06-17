"""
Tests for Sprint 5 Phase 1.3 — Alembic migration for User model.

The fixture below overrides SQLALCHEMY_DATABASE_URI to an in-memory SQLite DB
so migration tests run quickly and in isolation. The real DATABASE_URL is still
set first so the app factory's PostgreSQL validation passes at startup.
"""
import pytest
import tempfile
from cachelib import FileSystemCache
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from src import create_app, db


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
        # Override to SQLite for isolated migration unit tests only
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        # Clear cached engines so db uses the new SQLite URI
        if app_instance in db._app_engines:
            db._app_engines[app_instance].clear()
        app_instance.extensions.pop('sqlalchemy', None)
        db.init_app(app_instance)
        with app_instance.app_context():
            yield app_instance


def test_initial_migration_creates_users_table(app):
    """Verify the initial Alembic migration creates the users table."""
    with app.app_context():
        alembic_cfg = Config('migrations/alembic.ini')
        alembic_cfg.set_main_option('script_location', 'migrations')
        command.upgrade(alembic_cfg, 'head')

        # Verify users table exists with expected columns
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        assert 'users' in tables

        columns = {col['name']: col for col in inspector.get_columns('users')}
        assert 'id' in columns
        assert 'username' in columns
        assert 'email' in columns
        assert 'password_hash' in columns
        assert 'is_admin' in columns
        assert 'active_lessons' in columns
        assert 'created_at' in columns
        assert 'updated_at' in columns

        # Verify unique indexes were created
        indexes = {idx['name']: idx for idx in inspector.get_indexes('users')}
        assert indexes['ix_users_username']['unique']
        assert 'ix_users_email' in indexes
        assert indexes['ix_users_email']['unique']

        # Verify primary key
        pk = inspector.get_pk_constraint('users')
        assert pk['constrained_columns'] == ['id']


def test_migration_adds_generation_completed_at(app):
    """The latest migration must add the generation_completed_at
    column to study_paths. This is the canonical "navigate now"
    signal read by the JS via /lessons/generation-status.
    """
    with app.app_context():
        alembic_cfg = Config('migrations/alembic.ini')
        alembic_cfg.set_main_option('script_location', 'migrations')
        command.upgrade(alembic_cfg, 'head')

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        assert 'study_paths' in tables

        columns = {col['name']: col for col in inspector.get_columns('study_paths')}
        assert 'generation_completed_at' in columns, (
            "study_paths is missing the generation_completed_at "
            "column. The JS redirect signal relies on this column."
        )
        # The column must be nullable — the column is set when
        # generation completes, NULL while it is in progress.
        assert columns['generation_completed_at']['nullable'] is True
