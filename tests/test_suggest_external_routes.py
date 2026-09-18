"""Route tests for external suggestions branch."""
import json
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, Suggestion, User


@pytest.fixture
def ext_client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('WEB_SEARCH_ENABLED', 'false')
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config.update({
            'TESTING': True, 'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False, 'SECRET_KEY': 'test-secret',
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
            user = User(username='extuser', email='ex@example.com',
                        can_generate_lessons=True, tts_enabled=False)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _login(client):
    client.post('/login', data={'username': 'extuser', 'password': 'pass'})


def _seed_all_passed(app, user, title='Thermodynamics', fname='physics101.pdf'):
    with app.app_context():
        path = StudyPath(user_id=user.id, title='T', learning_goal='Learn thermodynamics physics',
                         status='active',
                         content_data=json.dumps([{
                             'index': 0, 'module_title': title,
                             'lesson': {'slides': []}, 'quiz': {'questions': []},
                             'checkpoints': {}, 'sources': [], 'difficulty': 'Normal',
                             'tts_enabled': False, 'completed': True,
                             'score': 90, 'passed': True}]),
                         modules_json=json.dumps([{'title': title}]),
                         summary_text='Physics textbook thermodynamics',
                         relevance_json='{}', file_names=json.dumps([fname]))
        db.session.add(path)
        db.session.commit()
        return path.id


def test_internal_empty_proprietary_returns_all_covered(ext_client, monkeypatch):
    app, user = ext_client
    monkeypatch.setenv('AI_MOCK', 'true')  # internal compute → mock, filtered as planned
    client = app.test_client()
    _login(client)
    with app.app_context():
        pid = _seed_all_passed(app, user, fname='HR_Handbook.pdf')
        # force proprietary summary
        p = StudyPath.query.get(pid)
        p.summary_text = 'Employee salaries and internal memo'
        p.learning_goal = 'HR onboarding'
        db.session.commit()
    r = client.get(f'/suggestions?path_id={pid}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['suggestions'] == []
    assert body['all_covered'] is True


def test_external_branch_persists_urls(monkeypatch, ext_client):
    app, user = ext_client
    monkeypatch.setenv('AI_MOCK', 'false')
    monkeypatch.setenv('WEB_SEARCH_ENABLED', 'true')
    import src.services.suggest_external as ext
    monkeypatch.setattr(ext, 'call_ollama', lambda prompt, model=None: json.dumps({
        "suggestions": [{"title": "Heat Engines", "reason": "Next.",
                         "source_refs": "web", "source_urls": ["https://real.example/h"]}]}))
    monkeypatch.setattr('src.services.web_search_service.web_search',
                        lambda q, max_results=5: [{'title': 'H', 'url': 'https://real.example/h', 'content': 'c'}])
    monkeypatch.setattr('src.services.web_search_service.web_fetch', lambda u, max_chars=6000: 'body')
    # compute_external imports web fns lazily; patch via suggest_external search passthrough
    orig_compute = ext.compute_external_suggestions

    def patched_compute(goal, modules=None, summary='', file_names=None, search_fn=None, fetch_fn=None,
                         **kw):
        import src.services.web_search_service as w
        return orig_compute(goal, modules, summary, file_names,
                            search_fn=w.web_search, fetch_fn=w.web_fetch, **kw)

    monkeypatch.setattr(ext, 'compute_external_suggestions', patched_compute)
    # internal must be empty: mock internal to [] via AI_MOCK? compute_suggestions uses call_ollama;
    # patch it to return empty suggestions JSON.
    import src.services.suggest_next as internal
    monkeypatch.setattr(internal, 'call_ollama', lambda prompt, model=None: '{"suggestions": []}')

    client = app.test_client()
    _login(client)
    with app.app_context():
        pid = _seed_all_passed(app, user)
    r = client.get(f'/suggestions?path_id={pid}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['source'] == 'web'
    assert len(body['suggestions']) == 1
    assert body['suggestions'][0]['is_external'] is True
    assert body['suggestions'][0]['source_urls'] == ['https://real.example/h']


def test_accept_external_creates_web_grounded_module(ext_client, monkeypatch):
    app, user = ext_client
    client = app.test_client()
    _login(client)
    with app.app_context():
        pid = _seed_all_passed(app, user)
        row = Suggestion(user_id=user.id, study_path_id=pid, title='Heat Engines',
                         reason='Next', source_refs='web', status='pending',
                         is_external=True, source_urls=json.dumps(['https://real.example/h']))
        db.session.add(row)
        db.session.commit()
        sid = row.id
    monkeypatch.setattr('src.services.web_search_service.web_fetch', lambda u, max_chars=6000: 'Carnot cycle body')
    import src.services.lesson_orchestrator as orch
    monkeypatch.setattr(orch, 'generate_quiz', lambda *a, **k: {'questions': [], 'fallback': False})
    monkeypatch.setattr(orch, 'generate_inline_checkpoint',
                        lambda *a, **k: {'type': 'mcq', 'prompt': 'P?', 'options': ['A'], 'answer_index': 0})
    import src.services.lesson_generator as lg
    monkeypatch.setattr(lg, 'generate_lesson', lambda *a, **k: {
        'module_title': 'Heat Engines', 'slides': [{'type': 'title', 'title': 'H', 'subtitle': 'S'}], 'sources': []})
    monkeypatch.setattr(lg, 'generate_narration_script', lambda *a, **k: [])
    r = client.post('/suggestions/accept', json={'suggestion_id': sid})
    assert r.status_code == 200
    assert '/lessons/' in r.get_json()['redirect']
