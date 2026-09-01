"""
Tests for the mascot memory store, line generator, and /mascot/line endpoint.

These tests use SQLite in-memory (mirroring the existing test fixtures) so
no external database is required.  The LLM is stubbed via AI_MOCK=true so
the line generator returns a deterministic fallback.
"""
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import MascotMemory, User
from src.services.mascot_lines import generate_line
from src.services.mascot_memory import (
    delete_all,
    get_memories,
    store_memory,
)
from src.services.mascot_persona import SYSTEM_PROMPT, build_context_block

# ── Shared app fixture ────────────────────────────────────────────────────


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    monkeypatch.setenv('AI_MOCK', 'true')
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


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    def _make(username='tester', password='testpass1', **kwargs):
        with app.app_context():
            user = User(username=username, email=f'{username}@example.com',
                        **kwargs)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return user.id
    return _make


def _login(client, username='tester', password='testpass1'):
    return client.post(
        '/login',
        data={'username': username, 'password': password},
        follow_redirects=False,
    )


# ── MascotMemory model ────────────────────────────────────────────────────


class TestMascotMemoryModel:
    def test_table_exists(self, app):
        assert MascotMemory.__tablename__ == 'mascot_memory'

    def test_valid_types(self):
        assert MascotMemory.VALID_TYPES == ('semantic', 'episodic', 'procedural')


# ── Memory store CRUD ────────────────────────────────────────────────────


class TestMemoryStore:
    def test_store_and_retrieve(self, app, make_user):
        uid = make_user()
        mem = store_memory(uid, 'episodic', 'Finished module 3 of Biology')
        assert mem is not None
        memories = get_memories(uid)
        assert len(memories) == 1
        assert memories[0]['memory_type'] == 'episodic'
        assert 'Finished module 3' in memories[0]['content']

    def test_store_invalid_type_returns_none(self, app, make_user):
        uid = make_user()
        result = store_memory(uid, 'invalid_type', 'content')
        assert result is None

    def test_store_empty_content_returns_none(self, app, make_user):
        uid = make_user()
        result = store_memory(uid, 'semantic', '   ')
        assert result is None

    def test_get_memories_newest_first(self, app, make_user):
        uid = make_user()
        store_memory(uid, 'semantic', 'first')
        store_memory(uid, 'episodic', 'second')
        memories = get_memories(uid)
        assert len(memories) == 2
        # 'second' was stored later → should be first (newest)
        assert memories[0]['content'] == 'second'

    def test_get_memories_unknown_user_returns_empty(self, app):
        assert get_memories('nonexistent') == []

    def test_delete_all(self, app, make_user):
        uid = make_user()
        store_memory(uid, 'semantic', 'a')
        store_memory(uid, 'episodic', 'b')
        count = delete_all(uid)
        assert count == 2
        assert get_memories(uid) == []


# ── Line generator ────────────────────────────────────────────────────────


class TestLineGenerator:
    def test_returns_nonempty_string(self, app, make_user):
        uid = make_user()
        line = generate_line(uid, 'Bobby', 'idle')
        assert isinstance(line, str)
        assert len(line) > 0

    def test_respects_max_length(self, app, make_user):
        uid = make_user()
        # Even with AI_MOCK (which returns a long mock), the line is
        # truncated or falls back to a short static line.
        line = generate_line(uid, 'Bobby', 'idle')
        assert len(line) <= 70

    def test_fallback_on_mock_mode(self, app, make_user):
        """AI_MOCK=true makes call_ollama return a mock — the line
        generator should still produce a usable line."""
        uid = make_user()
        line = generate_line(uid, 'Ali', 'dashboard')
        assert len(line) > 0
        assert len(line) <= 70

    def test_cache_returns_same_line(self, app, make_user):
        """Two consecutive calls with the same user+event should return
        the cached line (no second LLM call)."""
        uid = make_user()
        line1 = generate_line(uid, 'Bobby', 'idle')
        line2 = generate_line(uid, 'Bobby', 'idle')
        assert line1 == line2

    def test_never_raises_on_error(self, app, make_user):
        """generate_line must never raise — it always returns a string."""
        uid = make_user()
        # Pass None display_name — should still work
        line = generate_line(uid, '', 'error')
        assert isinstance(line, str)
        assert len(line) > 0


# ── Persona prompt ────────────────────────────────────────────────────────


class TestPersonaPrompt:
    def test_system_prompt_exists(self):
        assert len(SYSTEM_PROMPT) > 100
        assert '70 characters' in SYSTEM_PROMPT

    def test_build_context_block_with_memories(self):
        memories = [
            {'memory_type': 'episodic', 'content': 'Finished Biology quiz',
             'created_at': None},
        ]
        ctx = build_context_block(memories, 'Bobby',
                                  path_title='Cell Biology',
                                  progress_pct=60,
                                  event='idle')
        assert 'Bobby' in ctx
        assert 'Cell Biology' in ctx
        assert '60%' in ctx
        assert 'Learner Profile' in ctx
        assert 'Finished Biology quiz' in ctx

    def test_build_context_block_without_memories(self):
        ctx = build_context_block([], 'Ali', event='dashboard')
        assert 'Ali' in ctx
        assert 'Learner Profile' not in ctx


# ── /mascot/line endpoint ────────────────────────────────────────────────


class TestMascotLineEndpoint:
    def test_anonymous_redirected_to_login(self, client):
        resp = client.get('/mascot/line')
        assert resp.status_code in (302, 303)
        assert '/login' in resp.headers.get('Location', '')

    def test_authenticated_returns_json(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.get('/mascot/line?context=idle')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'text' in data
        assert len(data['text']) > 0
        assert data['text'] != ''

    def test_returns_talk_state_for_idle(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.get('/mascot/line?context=idle')
        data = resp.get_json()
        assert data['state'] == 'talk'

    def test_returns_error_state_for_error_context(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.get('/mascot/line?context=error')
        data = resp.get_json()
        assert data['state'] == 'error'

    def test_invalid_context_defaults_to_idle(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.get('/mascot/line?context=garbage')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'text' in data

    def test_never_exceeds_70_chars(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.get('/mascot/line?context=dashboard')
        data = resp.get_json()
        assert len(data['text']) <= 70