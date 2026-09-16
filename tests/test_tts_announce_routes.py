"""Route tests for Stage 2 announcements + Stage 1 grade memory fix."""
import json
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, User


@pytest.fixture
def announce_client(monkeypatch):
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
            user = User(username='announcer', email='an@example.com',
                        can_generate_lessons=True, tts_enabled=True,
                        tts_speaker='Emma', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _login(client, username='announcer'):
    client.post('/login', data={'username': username, 'password': 'pass'})


def _seed_lesson(app, user, title='Photosynthesis'):
    with app.app_context():
        path = StudyPath(user_id=user.id, title='T', learning_goal='G',
                         status='active', content_data=json.dumps([{
                             'index': 0, 'module_title': title,
                             'lesson': {'slides': [], 'narration': []},
                             'quiz': {'questions': [
                                 {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                                  'options': ['A', 'B'], 'answer_index': 0,
                                  'explanation': 'E'}]},
                             'checkpoints': {}, 'sources': [],
                             'difficulty': 'Normal', 'tts_enabled': True,
                             'tts_speaker': 'Emma', 'completed': False,
                             'score': None, 'passed': False,
                         }]),
                         modules_json=json.dumps([{'title': title}]),
                         summary_text='S', relevance_json='{}')
        db.session.add(path)
        db.session.commit()
        return path.id


def test_grade_includes_announcement_flag_and_memory_title(announce_client, monkeypatch, tmp_path):
    app, user = announce_client
    # Inline synthesis in POST grade must not touch the real data/tts dir
    # or the network in tests.
    from src.services import tts_service as tts_module
    monkeypatch.setattr(tts_module, 'TTS_DIR', tmp_path)
    monkeypatch.setattr(tts_module, 'ANNOUNCE_DIR', tmp_path / 'announcements')

    async def mock_mp3(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b'fake-audio')

    monkeypatch.setattr(tts_module, '_generate_mp3', mock_mp3)
    client = app.test_client()
    _login(client)
    path_id = _seed_lesson(app, user, title='Photosynthesis')
    resp = client.post(f'/lessons/0/grade?path_id={path_id}',
                       json={'answers': [0], 'checkpoint_answers': {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['announcement']['available'] is True
    assert data['announcement']['kind'] == 'lesson_complete'
    # Inline fast-path: synthesized during grading, no second round-trip.
    assert 'audio_url' in data['announcement']
    assert '/tts/announcements/' in data['announcement']['audio_url']
    with app.app_context():
        from src.services.mascot_memory import get_memories
        mems = get_memories(user.id, limit=5)
        assert any('Photosynthesis' in m['content'] for m in mems)


def test_grade_degrades_when_synthesis_fails(announce_client, monkeypatch, tmp_path):
    app, user = announce_client
    from src.services import tts_service as tts_module
    monkeypatch.setattr(tts_module, 'TTS_DIR', tmp_path)
    monkeypatch.setattr(tts_module, 'ANNOUNCE_DIR', tmp_path / 'announcements')

    async def boom(text, voice, out_path):
        raise RuntimeError('edge-tts down')

    monkeypatch.setattr(tts_module, '_generate_mp3', boom)
    client = app.test_client()
    _login(client)
    path_id = _seed_lesson(app, user, title='Photosynthesis')
    resp = client.post(f'/lessons/0/grade?path_id={path_id}',
                       json={'answers': [0], 'checkpoint_answers': {}})
    assert resp.status_code == 200
    data = resp.get_json()
    # Grading succeeds; client falls back to /tts/announce then results audio.
    assert data['score'] == 100
    assert data['announcement']['available'] is True
    assert 'audio_url' not in data['announcement']


def test_announce_requires_tts_and_serves_audio(announce_client, monkeypatch, tmp_path):
    app, user = announce_client
    from src.services import tts_service as tts_module
    monkeypatch.setattr(tts_module, 'TTS_DIR', tmp_path)
    monkeypatch.setattr(tts_module, 'ANNOUNCE_DIR', tmp_path / 'announcements')

    async def mock_mp3(text, voice, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b'fake-audio')

    monkeypatch.setattr(tts_module, '_generate_mp3', mock_mp3)
    client = app.test_client()
    _login(client)
    path_id = _seed_lesson(app, user)

    r = client.post('/tts/announce', json={
        'path_id': path_id, 'module_index': 0, 'kind': 'lesson_complete',
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    assert 'audio_url' in body

    ann_id = body['audio_url'].split('/tts/announcements/')[1].split('.mp3')[0]
    a = client.get(f'/tts/announcements/{ann_id}.mp3')
    assert a.status_code == 200

    # bad id rejected, other user isolated
    assert client.get('/tts/announcements/zzz.mp3').status_code == 404


def test_announce_404_when_tts_disabled(announce_client):
    app, user = announce_client
    client = app.test_client()
    with app.app_context():
        user.tts_enabled = False
        db.session.commit()
    _login(client)
    r = client.post('/tts/announce', json={'kind': 'suggestion'})
    assert r.status_code == 404
