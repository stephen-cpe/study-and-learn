"""
Regression tests for bugs found during autonomous E2E testing (Alice runs).

Covers: per-module RAG query honoring (B1/B7 root cause), near-duplicate
suggestion filtering (B5), StudyPath DB-fallback plan recovery (F0),
pending-suggestion coverage flag (B3), and lesson-fallback marking (B2).
"""
import json
import tempfile
from unittest.mock import patch

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, Suggestion, User


@pytest.fixture
def reg_app(monkeypatch):
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
            yield app
            db.session.remove()
            db.drop_all()


def _seed_path_without_content_data(app):
    """Seed a pre-generation path: plan only in modules_json (F0 shape)."""
    with app.app_context():
        user = User(username='reggie', email='r@example.com', can_generate_lessons=True)
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()
        path = StudyPath(
            user_id=user.id, title='MFA Guide', learning_goal='Learn MFA',
            status='active', content_data=None,
            file_hashes=json.dumps(['ab' * 32]),
            file_names=json.dumps(['doc.pdf']),
            modules_json=json.dumps([{'title': 'MFA Basics', 'estimated_effort': '1 hour'}]),
            summary_text='S', relevance_json=json.dumps({'relevance_label': 'strong'}),
        )
        db.session.add(path)
        db.session.commit()
        return user.id, path.id


def test_lesson_retriever_uses_module_query():
    """The per-module query must drive similarity search, not the goal."""
    from src.services.lesson_orchestrator import make_retriever_from_hashes_with_names
    with patch('src.services.lesson_orchestrator.build_rag_context_from_hashes_with_sources',
               return_value={'context_text': 'CHUNK', 'sources': []}) as mock_build:
        retriever = make_retriever_from_hashes_with_names('learning goal', ['h'], ['f.txt'])
        retriever('Data Classification Handling Rules')
    assert mock_build.call_args[0][0] == 'Data Classification Handling Rules'


def test_lesson_retriever_falls_back_to_goal_on_empty_query():
    from src.services.lesson_orchestrator import make_retriever_from_hashes_with_names
    with patch('src.services.lesson_orchestrator.build_rag_context_from_hashes_with_sources',
               return_value={'context_text': 'CHUNK', 'sources': []}) as mock_build:
        retriever = make_retriever_from_hashes_with_names('learning goal', ['h'], ['f.txt'])
        retriever('')
    assert mock_build.call_args[0][0] == 'learning goal'


def test_compute_suggestions_skips_near_duplicate(monkeypatch):
    """'X (SQL/NoSQL)' planned vs 'X' suggested must be treated as dup (B5)."""
    from src.services import suggest_next as sn

    def fake_call(prompt, **kw):
        return json.dumps({"suggestions": [
            {"title": "Backend Engineering: Flask APIs and Data Management",
             "reason": "dup", "source_refs": "doc"},
            {"title": "CI/CD Pipelines", "reason": "next", "source_refs": "doc"},
        ]})

    monkeypatch.setattr(sn, 'call_ollama', fake_call)
    out = sn.compute_suggestions(
        'G', [{'title': 'Backend Engineering: Flask APIs and Data Management (SQL/NoSQL)'}])
    assert [s['title'] for s in out['suggestions']] == ['CI/CD Pipelines']


def test_get_study_path_data_falls_back_to_modules_json(reg_app):
    """Fresh-session generate must recover the plan from modules_json (F0)."""
    from src.repositories.lesson_repo import get_study_path_data
    _seed_path_without_content_data(reg_app)
    with reg_app.app_context():
        user = User.query.filter_by(username='reggie').first()
        data = get_study_path_data(user)
    assert data is not None
    assert [m['title'] for m in data['modules']] == ['MFA Basics']


def test_pending_suggestions_report_not_covered(reg_app):
    """Pending rows must never come back with all_covered=True (B3)."""
    _seed_path_without_content_data(reg_app)
    client = reg_app.test_client()
    client.post('/login', data={'username': 'reggie', 'password': 'pass'})
    with reg_app.app_context():
        user = User.query.filter_by(username='reggie').first()
        path = StudyPath.query.filter_by(user_id=user.id).first()
        # All planned modules "passed" to force the old contradiction.
        db.session.add(Suggestion(user_id=user.id, study_path_id=path.id,
                                 title='Follow-up', reason='More',
                                 source_refs='doc', status='pending'))
        db.session.commit()
        path_id = path.id
    resp = client.get(f'/suggestions?path_id={path_id}')
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body['suggestions']) == 1
    assert body['all_covered'] is False


def test_generate_lesson_marks_fallback(monkeypatch):
    """Failed generation must be flagged so callers can surface it (B2)."""
    from src.services import lesson_generator as lg
    from src.services.exceptions import AIServiceError

    def boom(prompt, *a, **k):
        raise AIServiceError('cloud down')

    monkeypatch.setattr(lg, 'call_ollama', boom)
    out = lg.generate_lesson('Mod', 'Goal', retriever=lambda q, **k: {'context_text': 'c', 'sources': []})
    assert out['fallback'] is True

    monkeypatch.setattr(
        lg, 'call_ollama',
        lambda prompt, *a, **k: '{"module_title": "Mod", "slides": [{"type": "title", "title": "T", "subtitle": "S"}]}')
    out = lg.generate_lesson('Mod', 'Goal', retriever=lambda q, **k: {'context_text': 'c', 'sources': []})
    assert out['fallback'] is False
