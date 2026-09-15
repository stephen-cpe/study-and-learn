"""
Tests for suggest-next (slice 5): internal document-grounded follow-up
topics with Generate/Dismiss, backed by the Suggestion table and the
durable StudyPath snapshot (modules_json/summary_text/relevance_json).
"""
import json
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, Suggestion, User


@pytest.fixture
def sg_app(monkeypatch):
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


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


def _seed_user_and_path(app, mono_lessons=True):
    with app.app_context():
        user = User(username='suggester', email='s@example.com',
                    can_generate_lessons=True)
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()
        lessons = []
        if mono_lessons:
            lessons = [{
                'index': 0, 'module_title': 'Photosynthesis',
                'estimated_effort': '30 min',
                'lesson': {'module_title': 'Photosynthesis', 'slides': []},
                'quiz': {'questions': []}, 'checkpoints': {},
                'sources': [], 'difficulty': 'Normal',
                'tts_enabled': False, 'tts_speaker': None,
                'tts_audio_status': 'n/a',
                'completed': True, 'score': 90, 'passed': True,
            }]
        path = StudyPath(
            user_id=user.id, title='Bio', learning_goal='Learn biology',
            status='active', content_data=json.dumps(lessons),
            file_hashes=json.dumps(['ab' * 32]),
            modules_json=json.dumps([{'title': 'Photosynthesis'}]),
            summary_text='Plants convert light to energy.',
            relevance_json=json.dumps({'relevance_label': 'strong',
                                       'missing_material': 'Cellular respiration'}),
        )
        db.session.add(path)
        db.session.commit()
        return user.id, path.id


def test_build_suggestion_prompt_lists_states():
    from src.services.suggest_next import build_suggestion_prompt
    p = build_suggestion_prompt('Learn bio', [
        {'title': 'Photosynthesis', 'passed': True, 'score': 90},
        {'title': 'Respiration', 'passed': False},
    ], summary='S', missing_material='M')
    assert 'Photosynthesis' in p and 'passed' in p
    assert 'Respiration' in p and 'not passed' in p


def test_compute_suggestions_never_raises(monkeypatch):
    from src.services import suggest_next as sn
    monkeypatch.setattr(sn, 'call_ollama', lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    assert sn.compute_suggestions('G', []) == {'suggestions': []}


def test_compute_suggestions_skips_planned(monkeypatch):
    import json as _json

    from src.services import suggest_next as sn

    def fake_call(prompt, **kw):
        return _json.dumps({"suggestions": [
            {"title": "Photosynthesis", "reason": "dup", "source_refs": "doc"},
            {"title": "Cellular Respiration", "reason": "next", "source_refs": "ch.2"},
        ]})

    monkeypatch.setattr(sn, 'call_ollama', fake_call)
    out = sn.compute_suggestions('G', [{'title': 'Photosynthesis'}])
    assert [s['title'] for s in out['suggestions']] == ['Cellular Respiration']


def test_list_returns_pending_without_llm(sg_app, monkeypatch):
    _seed_user_and_path(sg_app)
    client = sg_app.test_client()
    _login(client, 'suggester', 'pass')
    with sg_app.app_context():
        user = User.query.filter_by(username='suggester').first()
        path = StudyPath.query.filter_by(user_id=user.id).first()
        db.session.add(Suggestion(user_id=user.id, study_path_id=path.id,
                                  title='Respiration', reason='Next in doc',
                                  source_refs='ch.2', status='pending'))
        db.session.commit()
        path_id = path.id
    import src.services.suggest_next as sn
    with monkeypatch.context() as m:
        m.setattr(sn, 'compute_suggestions',
                  lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not call LLM')))
        resp = client.get(f'/suggestions?path_id={path_id}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['suggestions']) == 1
    assert data['suggestions'][0]['title'] == 'Respiration'


def test_dismiss_marks_row(sg_app):
    _seed_user_and_path(sg_app)
    client = sg_app.test_client()
    _login(client, 'suggester', 'pass')
    with sg_app.app_context():
        user = User.query.filter_by(username='suggester').first()
        path = StudyPath.query.filter_by(user_id=user.id).first()
        row = Suggestion(user_id=user.id, study_path_id=path.id,
                         title='X', status='pending')
        db.session.add(row)
        db.session.commit()
        sid = row.id
    resp = client.post('/suggestions/dismiss', json={'suggestion_id': sid})
    assert resp.status_code == 200
    with sg_app.app_context():
        assert Suggestion.query.get(sid).status == 'dismissed'


def test_accept_generates_module(sg_app, monkeypatch):
    _seed_user_and_path(sg_app)
    client = sg_app.test_client()
    _login(client, 'suggester', 'pass')

    import src.routes.lessons as lessons_mod

    def fake_artifacts(*a, **k):
        return {
            'lesson': {'module_title': 'Respiration', 'slides': [], 'narration': []},
            'quiz': {'questions': []}, 'checkpoints': {}, 'sources': [],
        }

    monkeypatch.setattr(lessons_mod, 'build_module_artifacts', fake_artifacts)
    with sg_app.app_context():
        user = User.query.filter_by(username='suggester').first()
        user_id = user.id
        path = StudyPath.query.filter_by(user_id=user.id).first()
        row = Suggestion(user_id=user.id, study_path_id=path.id,
                         title='Cellular Respiration', reason='Next',
                         source_refs='ch.2', status='pending')
        db.session.add(row)
        db.session.commit()
        sid, path_id = row.id, path.id

    resp = client.post('/suggestions/accept', json={'suggestion_id': sid})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert '/lessons/1' in data['redirect']

    with sg_app.app_context():
        assert Suggestion.query.get(sid).status == 'accepted'
        lessons = json.loads(StudyPath.query.get(path_id).content_data)
        assert len(lessons) == 2
        assert lessons[1]['module_title'] == 'Cellular Respiration'
        from src.models import MascotMemory
        mems = MascotMemory.query.filter_by(user_id=user_id).all()
        assert any('Accepted suggestion' in (m.content or '') for m in mems)


def test_suggestions_isolated_per_user(sg_app):
    _seed_user_and_path(sg_app)
    client = sg_app.test_client()
    with sg_app.app_context():
        other = User(username='other', email='o@example.com', can_generate_lessons=True)
        other.set_password('pass')
        db.session.add(other)
        db.session.commit()
    _login(client, 'other', 'pass')
    with sg_app.app_context():
        path = StudyPath.query.first()
        path_id = path.id
    assert client.get(f'/suggestions?path_id={path_id}').status_code == 404
