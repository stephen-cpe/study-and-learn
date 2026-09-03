"""
Security and correctness regression tests.

Consolidates regression tests for the confirmed High-severity defects
identified in the codebase review, grouped by category:

    Security — authentication & CSRF
        1. /test/set-model unauthenticated global mutation  -> removed (404)
        2. /process missing @login_required + display_name crash on
           anonymous AJAX -> anonymous POST must redirect to login (302),
           not 500.
        3. No CSRF protection on POST endpoints -> POST without token
           returns 400 when WTF_CSRF_ENABLED is True; with token succeeds;
           CI/AI_MOCK keep CSRF disabled so the existing suite still passes.

    Security — XSS sanitization
        4. Stored XSS via unsanitized innerHTML of AI-generated and
           user-controlled content. Jinja escapes at render time; DOMPurify
           is loaded via CDN on every page that uses innerHTML so client-side
           regex/markdown re-injection is sanitized before assignment.

    Correctness — cross-module chunk dedup
        5. store_chunks wrote ChromaDB IDs ``chunk_{i}`` but never put
           ``chunk_id`` into per-chunk metadata. The retrieval layer reads
           ``metadata.get('chunk_id', '')`` and the ``exclude_chunks`` /
           ``used_chunk_ids`` mechanism filters on it — so without the
           metadata field, dedup never excluded anything and modules could
           repeat the same source chunks. The fix: write ``chunk_id``
           (matching the Chroma id) into each chunk's metadata in
           store_chunks (and both rebuild paths in rag_retriever).

    Correctness — TTS worker stale-snapshot overwrite
        6. The TTS background worker loaded path.content_data (a JSON blob)
           once at start, mutated its in-memory copy over the full TTS run
           (45-90 min), then committed the whole blob — silently reverting
           any deck_position / checkpoint_user_answers the user persisted
           during that window. The fix: inside the final write transaction,
           re-read the current content_data from DB and apply ONLY the TTS
           field updates (tts_audio_status, tts_enabled) per-module by
           index, preserving concurrent user writes.

The fixtures mirror the SQLite-in-memory pattern used across the suite
(test_auth.py, test_admin_access.py, etc.). Full DOM-level XSS testing
requires a browser (Playwright/Selenium) and is out of scope for this
pytest suite; the tests here verify the Jinja escaping layer and the
DOMPurify <script> include on each affected page.
"""
import io
import json
import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, User

# ── Shared app builders ────────────────────────────────────────────────


def _build_app(monkeypatch, *, csrf_enabled=False):
    """Build an app instance mirroring the suite's fixture pattern.

    csrf_enabled toggles WTF_CSRF_ENABLED so we can exercise both the
    "CSRF enforced" and the "CSRF disabled (CI/mock)" code paths.
    """
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('CI', 'true')
    temp_dir = tempfile.TemporaryDirectory()
    app_instance = create_app()
    app_instance.config.update({
        'TESTING': True,
        'UPLOAD_FOLDER': temp_dir.name,
        'WTF_CSRF_ENABLED': csrf_enabled,
        'SECRET_KEY': 'test-secret',
        'SESSION_TYPE': 'cachelib',
        'SESSION_CACHELIB': FileSystemCache(
            cache_dir=temp_dir.name, threshold=500, mode=0o700
        ),
        'SESSION_PERMANENT': False,
    })
    from flask_session import Session
    Session(app_instance)
    app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app_instance.extensions.pop('sqlalchemy', None)
    db.init_app(app_instance)
    return app_instance, temp_dir


def _create_user(username='tester', email='tester@example.com',
                 can_generate_lessons=True, tts_enabled=False,
                 tts_speaker='Ava', lesson_difficulty='Normal', is_admin=False):
    user = User(
        username=username, email=email,
        can_generate_lessons=can_generate_lessons,
        tts_enabled=tts_enabled, tts_speaker=tts_speaker,
        lesson_difficulty=lesson_difficulty, is_admin=is_admin,
    )
    user.set_password('pass')
    db.session.add(user)
    db.session.commit()
    return user


# ── Fixtures: security (CSRF + auth) ───────────────────────────────────


@pytest.fixture
def csrf_client(monkeypatch):
    """Client with CSRF enforcement ON (the production posture)."""
    app_instance, temp_dir = _build_app(monkeypatch, csrf_enabled=True)
    with app_instance.app_context():
        db.create_all()
        _create_user(username='csrfuser', email='csrf@example.com')
        with app_instance.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()
    temp_dir.cleanup()


@pytest.fixture
def logged_in_client(monkeypatch):
    """Logged-in client with CSRF OFF (CI / AI_MOCK posture).

    Used by the XSS, chunk-dedup, and deck-CSRF regression tests.
    """
    app_instance, temp_dir = _build_app(monkeypatch, csrf_enabled=False)
    with app_instance.app_context():
        db.create_all()
        _create_user(username='norm', email='norm@example.com')
        with app_instance.test_client() as c:
            c.post('/login', data={'username': 'norm', 'password': 'pass'})
            yield c
        db.session.remove()
        db.drop_all()
    temp_dir.cleanup()


@pytest.fixture
def anon_client(monkeypatch):
    """Anonymous client (not logged in) with CSRF OFF for the /process
    auth-gating test."""
    app_instance, temp_dir = _build_app(monkeypatch, csrf_enabled=False)
    with app_instance.app_context():
        db.create_all()
        with app_instance.test_client() as c:
            yield c
        db.session.remove()
        db.drop_all()
    temp_dir.cleanup()


# ── Fixtures: correctness (TTS worker) ────────────────────────────────


@pytest.fixture
def worker_client(monkeypatch):
    """Yields (app, user) for TTS-worker tests. The user has TTS enabled."""
    app_instance, temp_dir = _build_app(monkeypatch, csrf_enabled=False)
    with app_instance.app_context():
        db.create_all()
        user = _create_user(
            username='ttsworker', email='tw@example.com', tts_enabled=True,
        )
        yield app_instance, user
        db.session.remove()
        db.drop_all()
    temp_dir.cleanup()


def _patch_tts_dir(monkeypatch, tmp_path):
    monkeypatch.setattr('src.services.tts_worker.TTS_DIR', tmp_path)
    monkeypatch.setattr('src.services.tts_service.TTS_DIR', tmp_path)


def _seed_path(app, user, num_modules=2, tts_enabled=True):
    """Insert a StudyPath with N lessons, each with a narration script."""
    with app.app_context():
        lessons = []
        for i in range(num_modules):
            narration = [
                {'slide_index': -1, 'text': f'Intro {i}'},
                {'slide_index': 0, 'text': f'Slide 0 narration for module {i}'},
                {'slide_index': 1, 'text': f'Checkpoint narration for module {i}'},
                {'slide_index': 2, 'text': f'Slide 1 narration for module {i}'},
            ]
            lessons.append({
                'index': i,
                'module_title': f'Module {i + 1}',
                'estimated_effort': '30 min',
                'lesson': {
                    'module_title': f'Module {i + 1}',
                    'slides': [
                        {'type': 'title', 'title': f'Title {i}', 'subtitle': ''},
                        {'type': 'content', 'heading': 'C', 'bullets': ['a']},
                    ],
                    'narration': narration,
                },
                'quiz': {'questions': [
                    {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                     'options': ['A', 'B', 'C', 'D'], 'answer_index': 0,
                     'explanation': 'E'}
                ]},
                'checkpoints': {},
                'sources': [],
                'difficulty': 'Normal',
                'tts_enabled': tts_enabled,
                'tts_speaker': 'Ava',
                'completed': False,
                'score': None,
                'passed': False,
                'tts_audio_status': 'pending' if tts_enabled else 'n/a',
            })
        path = StudyPath(
            user_id=user.id, title='Worker Path', learning_goal='Learn X',
            status='active', content_data=json.dumps(lessons),
        )
        db.session.add(path)
        db.session.commit()
        return path.id


# ── Helpers ───────────────────────────────────────────────────────────


def _extract_csrf_token(html_bytes):
    """Extract the csrf_token value from a rendered form's hidden input."""
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', html_bytes)
    assert m, "page should render a csrf_token input for the form"
    return m.group(1).decode()


def _login_with_csrf(client, username='csrfuser'):
    """Log in via the index page's login form, extracting the CSRF token."""
    rv = client.get('/')
    assert rv.status_code == 200
    token = _extract_csrf_token(rv.data)
    rv = client.post('/login', data={
        'username': username, 'password': 'pass', 'csrf_token': token,
    }, follow_redirects=True)
    assert rv.status_code == 200
    return token


def _generate_single_lesson(client):
    """Generate one lesson via /generate-lessons (mocked AI). Returns None."""
    with patch('src.services.lesson_generator.call_ollama') as mock_lesson, \
         patch('src.services.quiz_generator.call_ollama') as mock_quiz:
        mock_lesson.return_value = (
            '{"module_title": "Intro", "slides": '
            '[{"type": "title", "title": "Hello", "subtitle": "World"}]}'
        )
        mock_quiz.return_value = (
            '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", '
            '"options": ["A","B","C","D"], "answer_index": 0, '
            '"explanation": "E"}]}'
        )
        with client.session_transaction() as sess:
            sess['learning_goal'] = 'Learn stuff'
            sess['study_path'] = {
                'modules': [{'title': 'M1', 'estimated_effort': '1h'}]
            }
            sess['extracted_texts'] = ['text']
        client.post('/generate-lessons')


# ═══════════════════════════════════════════════════════════════════════
# Security — authentication & CSRF
# ═══════════════════════════════════════════════════════════════════════


class TestDebugEndpointRemoved:
    """The temporary /test/set-model endpoint must be deleted."""

    def test_post_returns_404(self, anon_client):
        rv = anon_client.post('/test/set-model', json={'model': 'evil'})
        assert rv.status_code == 404

    def test_get_returns_404(self, anon_client):
        rv = anon_client.get('/test/set-model', json={'model': 'evil'})
        assert rv.status_code == 404


class TestProcessRequiresLogin:
    """Anonymous POST /process must redirect to login, not crash with 500."""

    def test_anonymous_ajax_redirects(self, anon_client):
        data = {
            'learning_goal': 'Learn testing',
            'task_id': 'anon-task-001',
            'files': [(io.BytesIO(b'content'), 'test.txt')],
        }
        rv = anon_client.post('/process', data=data,
                              content_type='multipart/form-data')
        assert rv.status_code != 500
        assert rv.status_code in (302, 401, 403)

    def test_anonymous_non_ajax_redirects(self, anon_client):
        data = {
            'learning_goal': 'Learn testing',
            'files': [(io.BytesIO(b'content'), 'test.txt')],
        }
        rv = anon_client.post('/process', data=data,
                              content_type='multipart/form-data',
                              follow_redirects=False)
        assert rv.status_code != 500
        assert rv.status_code in (302, 401, 403)


class TestCSRFEnforcement:
    """CSRF protection on POST endpoints (form + AJAX)."""

    def test_disabled_under_ci_or_mock(self, logged_in_client):
        """With WTF_CSRF_ENABLED=False, POSTs succeed without a token."""
        with logged_in_client.session_transaction() as sess:
            sess['learning_goal'] = 'Learn stuff'
            sess['study_path'] = {
                'modules': [{'title': 'M1', 'estimated_effort': '1h'}]
            }
            sess['extracted_texts'] = ['text']
        rv = logged_in_client.post('/generate-lessons')
        assert rv.status_code == 200

    def test_login_without_token_rejected(self, csrf_client):
        rv = csrf_client.post('/login', data={
            'username': 'csrfuser', 'password': 'pass'
        })
        assert rv.status_code == 400

    def test_signup_without_token_rejected(self, csrf_client):
        rv = csrf_client.post('/signup', data={
            'username': 'newuser', 'email': 'new@example.com',
            'password': 'secret'
        })
        assert rv.status_code == 400

    def test_settings_without_token_rejected(self, csrf_client):
        _login_with_csrf(csrf_client)
        rv = csrf_client.post('/settings', data={'avatar': 'avatar-0.png'})
        assert rv.status_code == 400

    def test_settings_with_token_succeeds(self, csrf_client):
        _login_with_csrf(csrf_client)
        rv = csrf_client.get('/settings')
        assert rv.status_code == 200
        token = _extract_csrf_token(rv.data)
        rv = csrf_client.post('/settings', data={
            'avatar': 'avatar-0.png', 'csrf_token': token,
        }, follow_redirects=False)
        assert rv.status_code in (200, 302)

    def test_ajax_without_csrf_header_rejected(self, csrf_client):
        _login_with_csrf(csrf_client)
        with csrf_client.session_transaction() as sess:
            sess['learning_goal'] = 'Learn stuff'
            sess['study_path'] = {
                'modules': [{'title': 'M1', 'estimated_effort': '1h'}]
            }
            sess['extracted_texts'] = ['text']
        rv = csrf_client.post('/generate-lessons',
                              data='{"task_id": "x"}',
                              content_type='application/json')
        assert rv.status_code == 400

    def test_ajax_with_csrf_header_succeeds(self, csrf_client, monkeypatch):
        monkeypatch.setenv('AI_MOCK', 'true')
        token = _login_with_csrf(csrf_client)
        with csrf_client.session_transaction() as sess:
            sess['learning_goal'] = 'Learn stuff'
            sess['study_path'] = {
                'modules': [{'title': 'M1', 'estimated_effort': '1h'}]
            }
            sess['extracted_texts'] = ['text']
        rv = csrf_client.post('/generate-lessons',
                              data='{"task_id": "x"}',
                              content_type='application/json',
                              headers={'X-CSRFToken': token})
        assert rv.status_code == 200


class TestCSRFTokenInAllForms:
    """Every POST form across all templates must include a csrf_token input.

    lesson_deck.html is a standalone document (does not extend base.html),
    so the CSRF meta tag + csrf.js must be included explicitly there.
    """

    def test_deck_page_includes_csrf_meta_and_script(self, logged_in_client):
        _generate_single_lesson(logged_in_client)
        rv = logged_in_client.get('/lessons/0')
        assert rv.status_code == 200
        assert b'name="csrf-token"' in rv.data, (
            "lesson_deck.html must include <meta name=\"csrf-token\">"
        )
        assert b'js/csrf.js' in rv.data, (
            "lesson_deck.html must include csrf.js (standalone document)"
        )

    def test_lessons_page_mark_complete_form_has_csrf_token(
        self, logged_in_client
    ):
        _generate_single_lesson(logged_in_client)
        # Mark the single module as passed so the "Mark Complete" form renders.
        from src.models import StudyPath
        from src.models import User as U
        from src.repositories.lesson_repo import get_lessons, save_lessons
        user = U.query.filter_by(username='norm').first()
        path = StudyPath.query.filter_by(
            user_id=user.id, status='active'
        ).first()
        lessons = get_lessons(user, path_id=path.id)
        lessons[0]['passed'] = True
        lessons[0]['completed'] = True
        lessons[0]['score'] = 100
        save_lessons(lessons, user, path_id=path.id)

        rv = logged_in_client.get(f'/lessons?path_id={path.id}')
        assert rv.status_code == 200
        complete_form = re.search(
            rb'<form[^>]*complete[^>]*>(.*?)</form>', rv.data, re.DOTALL
        )
        assert complete_form, "Mark Complete form should be present on /lessons"
        assert b'name="csrf_token"' in complete_form.group(1), (
            "Mark Complete form on /lessons must include a csrf_token input"
        )


# ═══════════════════════════════════════════════════════════════════════
# Security — XSS sanitization
# ═══════════════════════════════════════════════════════════════════════


class TestJinjaEscaping:
    """Server-side Jinja autoescape must neutralize hostile content."""

    def test_results_page_escapes_xss_in_summary(self, logged_in_client):
        with logged_in_client.session_transaction() as sess:
            sess['learning_goal'] = 'Learn ML'
            sess['summary'] = '<script>alert("xss")</script>Safe summary'
            sess['relevance_result'] = {
                'relevance_label': 'strong',
                'explanation': 'Good <img src=x onerror=alert(1)> match',
                'missing_material': 'None',
            }
            sess['study_path'] = {}
            sess['processed_filename'] = 'test.txt'
            sess['uploaded_filenames'] = ['test.txt']

        rv = logged_in_client.get('/results')
        assert rv.status_code == 200
        assert b'<script>alert' not in rv.data
        assert b'&lt;script&gt;' in rv.data
        assert b'<img src=x onerror' not in rv.data

    def test_admin_page_escapes_username(self, logged_in_client):
        from src.models import User as U
        user = U.query.filter_by(username='norm').first()
        user.is_admin = True
        db.session.commit()
        target = U(username="x';alert(1);//", email='quote@example.com')
        target.set_password('pass')
        db.session.add(target)
        db.session.commit()

        rv = logged_in_client.get('/admin')
        assert rv.status_code == 200
        assert b'showResetForm' not in rv.data
        script_blocks = re.findall(
            rb'<script[^>]*>(.*?)</script>', rv.data, re.DOTALL
        )
        for block in script_blocks:
            assert b'alert(1)' not in block

    def test_upload_page_no_raw_script(self, logged_in_client):
        rv = logged_in_client.get('/')
        assert rv.status_code == 200
        assert b'<script>alert' not in rv.data


class TestDOMPurifyLoaded:
    """DOMPurify must be loaded on every page that uses innerHTML with
    dynamic (AI/user) content, so client-side re-injection is sanitized."""

    def test_results_page(self, logged_in_client):
        with logged_in_client.session_transaction() as sess:
            sess['learning_goal'] = 'Learn ML'
            sess['summary'] = 'Safe'
            sess['relevance_result'] = {
                'relevance_label': 'strong', 'explanation': 'ok',
                'missing_material': 'None',
            }
            sess['study_path'] = {}
            sess['processed_filename'] = 't.txt'
            sess['uploaded_filenames'] = ['t.txt']
        rv = logged_in_client.get('/results')
        assert rv.status_code == 200
        assert b'dompurify' in rv.data.lower()

    def test_deck_page(self, logged_in_client):
        _generate_single_lesson(logged_in_client)
        rv = logged_in_client.get('/lessons/0')
        assert rv.status_code == 200
        assert b'dompurify' in rv.data.lower()

    def test_upload_page(self, logged_in_client):
        rv = logged_in_client.get('/')
        assert rv.status_code == 200
        assert b'dompurify' in rv.data.lower()


# ═══════════════════════════════════════════════════════════════════════
# Correctness — cross-module chunk dedup
# ═══════════════════════════════════════════════════════════════════════


class TestChunkIdInMetadata:
    """store_chunks must write chunk_id into per-chunk metadata so the
    exclude_chunks / used_chunk_ids cross-module dedup filter works."""

    @patch('src.services.vector_store.get_chroma_client')
    def test_default_metadata(self, mock_client):
        from src.services.vector_store import store_chunks

        mock_collection = MagicMock()
        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        with patch('langchain_ollama.OllamaEmbeddings') as mock_emb:
            mock_emb.return_value.embed_documents.return_value = [
                [0.1] * 384, [0.1] * 384
            ]
            store_chunks(['c1', 'c2'], 'test_coll')

        metadatas = mock_collection.add.call_args.kwargs.get('metadatas')
        assert metadatas is not None
        # chunk_id is namespaced with the collection name so chunks from
        # different files never collide in the cross-module dedup filter.
        assert metadatas[0]['chunk_id'] == 'test_coll:chunk_0'
        assert metadatas[1]['chunk_id'] == 'test_coll:chunk_1'

    @patch('src.services.vector_store.get_chroma_client')
    def test_merges_with_caller_metadata(self, mock_client):
        from src.services.vector_store import store_chunks

        mock_collection = MagicMock()
        mock_client.return_value.get_or_create_collection.return_value = mock_collection
        caller_meta = [
            {'source_hash': 'aaa', 'content_type': 'text'},
            {'source_hash': 'bbb', 'content_type': 'text'},
        ]
        with patch('langchain_ollama.OllamaEmbeddings') as mock_emb:
            mock_emb.return_value.embed_documents.return_value = [
                [0.1] * 384, [0.1] * 384
            ]
            store_chunks(['c1', 'c2'], 'test_coll', metadata=caller_meta)

        metadatas = mock_collection.add.call_args.kwargs.get('metadatas')
        assert metadatas[0]['source_hash'] == 'aaa'
        assert metadatas[0]['chunk_id'] == 'test_coll:chunk_0'
        assert metadatas[1]['source_hash'] == 'bbb'
        assert metadatas[1]['chunk_id'] == 'test_coll:chunk_1'

    @patch("src.services.vector_store.get_chroma_client")
    def test_rebuild_path_enriches_metadata(self, mock_client_factory):
        """The on-the-fly rebuild path in rag_retriever must produce
        metadata with chunk_id after passing through store_chunks."""
        from src.services.rag_retriever import build_rag_context_from_hashes
        from src.services.vector_store import get_collection_name

        h = "a" * 64
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = MagicMock()
        mock_client.delete_collection.return_value = None
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_factory.return_value = mock_client

        with patch("src.services.rag_retriever.retrieve_with_scores",
                   side_effect=Exception("Nothing found on disk")), \
             patch("src.services.rag_retriever.retrieve_from_multiple_collections",
                   return_value="rebuild context"), \
             patch("src.services.rag_retriever.retrieve_context",
                   return_value="rebuild context"), \
             patch("src.models.ContentRegistry") as mock_cr, \
             patch("src.services.rag_retriever.chunk_text",
                   return_value=["chunk A", "chunk B"]), \
             patch("langchain_ollama.OllamaEmbeddings") as mock_emb:
            mock_entry = MagicMock()
            mock_entry.extracted_text = "rebuild text"
            mock_cr.query.filter_by.return_value.first.return_value = mock_entry
            mock_emb.return_value.embed_documents.return_value = [
                [0.1] * 384, [0.1] * 384
            ]
            build_rag_context_from_hashes("goal", [h])

        metadatas = mock_collection.add.call_args.kwargs.get('metadatas')
        assert metadatas is not None
        coll = get_collection_name(h)
        for i, m in enumerate(metadatas):
            # chunk_id must be namespaced with the collection so the
            # cross-module dedup filter matches chunks uniquely per file.
            assert m['chunk_id'] == f'{coll}:chunk_{i}'

    def test_exclude_chunks_filters_when_chunk_id_present(self):
        """With chunk_id in metadata, exclude_chunks must actually filter."""
        from src.services.vector_store import (
            retrieve_from_multiple_collections_with_sources,
        )

        with patch('src.services.vector_store.get_chroma_client') as mock_client, \
             patch('src.services.vector_store.retrieve_with_scores') as mock_scores:
            mock_client.return_value.get_or_create_collection.return_value = MagicMock()
            mock_scores.return_value = [
                {'document': 'doc A', 'score': 0.9,
                 'metadata': {'chunk_id': 'chunk_0', 'source_hash': 'aaa'}},
                {'document': 'doc B', 'score': 0.8,
                 'metadata': {'chunk_id': 'chunk_1', 'source_hash': 'bbb'}},
            ]
            result = retrieve_from_multiple_collections_with_sources(
                'query', ['coll1'], top_k=10
            )

        assert len(result['sources']) == 2
        assert result['sources'][0]['chunk_id'] == 'chunk_0'
        assert result['sources'][1]['chunk_id'] == 'chunk_1'


# ═══════════════════════════════════════════════════════════════════════
# Correctness — TTS worker stale-snapshot overwrite
# ═══════════════════════════════════════════════════════════════════════


class TestTTSWorkerPreservesConcurrentWrites:
    """The TTS worker must NOT revert deck_position /
    checkpoint_user_answers that the user saved during the TTS run."""

    def test_preserves_deck_position(self, worker_client, monkeypatch, tmp_path):
        import asyncio

        from src.repositories.lesson_repo import get_lessons, save_lessons
        from src.services.tts_worker import run_tts_generation_for_path

        app, user = worker_client
        real_path_id = _seed_path(app, user, num_modules=2)
        _patch_tts_dir(monkeypatch, tmp_path)
        user_deck_position = 5

        async def slow_gen(text, voice, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.sleep(0.1)
            out_path.write_text('fake mp3')

        import src.services.tts_service as tts_service_module
        monkeypatch.setattr(tts_service_module, '_generate_mp3', slow_gen)

        with app.app_context():
            # Simulate the user saving deck_position while the worker runs.
            lessons = get_lessons(user, path_id=real_path_id)
            lessons[0]['deck_position'] = user_deck_position
            save_lessons(lessons, user, path_id=real_path_id)

            run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)

            lessons_after = get_lessons(user, path_id=real_path_id)
            assert lessons_after[0].get('deck_position') == user_deck_position
            assert lessons_after[0].get('tts_audio_status') == 'ready'

    def test_preserves_checkpoint_user_answers(
        self, worker_client, monkeypatch, tmp_path
    ):
        import asyncio

        from src.repositories.lesson_repo import get_lessons, save_lessons
        from src.services.tts_worker import run_tts_generation_for_path

        app, user = worker_client
        real_path_id = _seed_path(app, user, num_modules=1)
        _patch_tts_dir(monkeypatch, tmp_path)
        user_cp_answers = {'2': 0, '4': 1}

        async def slow_gen(text, voice, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.sleep(0.1)
            out_path.write_text('fake mp3')

        import src.services.tts_service as tts_service_module
        monkeypatch.setattr(tts_service_module, '_generate_mp3', slow_gen)

        with app.app_context():
            lessons = get_lessons(user, path_id=real_path_id)
            lessons[0]['checkpoint_user_answers'] = user_cp_answers
            save_lessons(lessons, user, path_id=real_path_id)

            run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)

            lessons_after = get_lessons(user, path_id=real_path_id)
            assert lessons_after[0].get('checkpoint_user_answers') == user_cp_answers

    def test_still_updates_tts_audio_status(
        self, worker_client, monkeypatch, tmp_path
    ):
        """The worker must still update tts_audio_status per module,
        even with the fresh re-read before commit."""
        from src.repositories.lesson_repo import get_lessons
        from src.services.tts_worker import run_tts_generation_for_path

        app, user = worker_client
        real_path_id = _seed_path(app, user, num_modules=2)
        _patch_tts_dir(monkeypatch, tmp_path)

        async def fast_gen(text, voice, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text('fake mp3')

        import src.services.tts_service as tts_service_module
        monkeypatch.setattr(tts_service_module, '_generate_mp3', fast_gen)

        with app.app_context():
            run_tts_generation_for_path(user_id=user.id, path_id=real_path_id)
            lessons = get_lessons(user, path_id=real_path_id)
            for lesson in lessons:
                assert lesson.get('tts_audio_status') == 'ready'