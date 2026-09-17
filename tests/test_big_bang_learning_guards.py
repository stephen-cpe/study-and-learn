"""Big-bang tests: partial credit, persisted results + weak strip,
pipeline singleflight, mascot prune/forget-me, and client resume hooks."""
import io
import json
import pathlib
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, User


@pytest.fixture
def bb_client(monkeypatch):
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
            user = User(username='bigbang', email='bb@example.com',
                        can_generate_lessons=True)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _login(client, username='bigbang'):
    client.post('/login', data={'username': username, 'password': 'pass'})


# ── #2 Partial credit ──────────────────────────────────────────────

def test_partial_credit_ordering_fractions():
    from src.services.grader import grade_partial_credit
    q = {'type': 'ordering', 'items': ['A', 'B', 'C', 'D'],
         'answer_order': [0, 1, 2, 3]}
    assert grade_partial_credit(q, [0, 1, 2, 3]) == 1.0
    assert grade_partial_credit(q, [0, 1, 2, 0]) == 0.75
    assert grade_partial_credit(q, [0, 1, 3, 2]) == 0.5
    assert grade_partial_credit(q, [0, 1, 2]) == 0.0
    assert grade_partial_credit(q, 'nope') == 0.0
    assert grade_partial_credit(q, None) == 0.0


def test_partial_credit_matching_fractions():
    from src.services.grader import grade_partial_credit
    q = {'type': 'matching', 'lefts': ['A', 'B'],
         'rights': ['2', '1'], 'answer_indices': [1, 0]}
    assert grade_partial_credit(q, [1, 0]) == 1.0
    assert grade_partial_credit(q, [1, 1]) == 0.5
    assert grade_partial_credit(q, [0, 1]) == 0.0
    assert grade_partial_credit(q, None) == 0.0


def test_partial_credit_delegates_other_types():
    from src.services.grader import grade_partial_credit
    mcq = {'type': 'mcq', 'answer_index': 2}
    assert grade_partial_credit(mcq, 2) == 1.0
    assert grade_partial_credit(mcq, 0) == 0.0
    assert grade_partial_credit({'type': 'bogus'}, 'x') == 0.0
    assert grade_partial_credit(None, None) == 0.0


def _seed_partial_lesson(app, user):
    with app.app_context():
        path = StudyPath(
            user_id=user.id, title='P', learning_goal='G', status='active',
            content_data=json.dumps([{
                'index': 0, 'module_title': 'M1',
                'lesson': {'slides': []},
                'quiz': {'questions': [
                    {'id': 'q1', 'type': 'mcq', 'prompt': 'MCQ?',
                     'options': ['A', 'B'], 'answer_index': 0, 'explanation': 'E'},
                    {'id': 'q2', 'type': 'ordering', 'prompt': 'Order.',
                     'items': ['A', 'B', 'C', 'D'], 'answer_order': [0, 1, 2, 3],
                     'explanation': 'E'},
                ]},
                'checkpoints': {}, 'sources': [], 'difficulty': 'Normal',
                'tts_enabled': False, 'completed': False,
                'score': None, 'passed': False,
            }]),
            modules_json=json.dumps([{'title': 'M1'}]),
            summary_text='S', relevance_json='{}')
        db.session.add(path)
        db.session.commit()
        return path.id


def test_grade_applies_partial_credit_and_persists_detail(bb_client):
    app, user = bb_client
    client = app.test_client()
    _login(client)
    path_id = _seed_partial_lesson(app, user)
    # mcq correct (1.0) + ordering 3/4 (0.75) over 2 points → 88%.
    resp = client.post(f'/lessons/0/grade?path_id={path_id}',
                       json={'answers': [0, [0, 1, 2, 0]], 'checkpoint_answers': {}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['score'] == 88
    assert data['passed'] is True
    assert data['quiz_results'][1]['credit'] == 0.75
    assert data['quiz_results'][1]['correct'] is False
    with app.app_context():
        path = StudyPath.query.get(path_id)
        lessons = json.loads(path.content_data)
        detail = lessons[0].get('results_detail')
        assert detail is not None
        assert detail['score'] == 88
        assert len(detail['quiz']) == 2


# ── #1 Weak-topics strip ───────────────────────────────────────────

def _seed_weak_lesson(app, user):
    with app.app_context():
        path = StudyPath(
            user_id=user.id, title='P', learning_goal='G', status='active',
            content_data=json.dumps([{
                'index': 0, 'module_title': 'Cells',
                'lesson': {'slides': []}, 'quiz': {'questions': []},
                'checkpoints': {}, 'sources': [], 'difficulty': 'Normal',
                'tts_enabled': False, 'completed': True,
                'score': 40, 'passed': False,
                'results_detail': {
                    'score': 40, 'passed': False, 'earned': 0.8, 'total': 2,
                    'at': '2026-01-01T00:00:00+00:00',
                    'quiz': [
                        {'id': 'q1', 'type': 'mcq', 'prompt': 'What is osmosis?',
                         'user_answer': 1, 'correct_answer': 0, 'correct': False,
                         'credit': 0.0, 'explanation': 'E'},
                        {'id': 'q2', 'type': 'ordering', 'prompt': 'Order mitosis.',
                         'user_answer': [0, 1, 3, 2], 'correct_answer': [0, 1, 2, 3],
                         'correct': False, 'credit': 0.5, 'explanation': 'E'},
                    ],
                    'checkpoints': [],
                },
            }]),
            modules_json=json.dumps([{'title': 'Cells'}]),
            summary_text='S', relevance_json='{}')
        db.session.add(path)
        db.session.commit()
        return path.id


def test_lessons_page_shows_weak_signals(bb_client):
    app, user = bb_client
    client = app.test_client()
    _login(client)
    path_id = _seed_weak_lesson(app, user)
    body = client.get(f'/lessons?path_id={path_id}').get_data(as_text=True)
    assert 'Weak Signals' in body
    assert 'What is osmosis?' in body
    assert 'Order mitosis.' in body
    assert 'weak-card' in body


def test_lessons_page_hides_weak_signals_when_clean(bb_client):
    app, user = bb_client
    client = app.test_client()
    _login(client)
    with app.app_context():
        path = StudyPath(
            user_id=user.id, title='P', learning_goal='G', status='active',
            content_data=json.dumps([{
                'index': 0, 'module_title': 'M1', 'lesson': {'slides': []},
                'quiz': {'questions': []}, 'checkpoints': {}, 'sources': [],
                'difficulty': 'Normal', 'tts_enabled': False,
                'completed': True, 'score': 100, 'passed': True,
            }]),
            modules_json=json.dumps([{'title': 'M1'}]),
            summary_text='S', relevance_json='{}')
        db.session.add(path)
        db.session.commit()
        path_id = path.id
    body = client.get(f'/lessons?path_id={path_id}').get_data(as_text=True)
    assert 'Weak Signals' not in body


# ── #3 Singleflight ────────────────────────────────────────────────

def test_claim_oldest_wins_and_same_goal_resumes(bb_client):
    app, user = bb_client
    with app.app_context():
        from src.services import background_tasks as _bt
        _bt.create_task('old-task', user.id, kind='process',
                        label='Processing: Same goal')
        winner, existing, same = _bt.claim_pipeline_task(
            'new-task', user.id, kind='process',
            label='Processing: Same goal', match_label='Processing: Same goal')
        assert winner is False
        assert existing == 'old-task'
        assert same is True


def test_claim_different_goal_reports_busy(bb_client):
    app, user = bb_client
    with app.app_context():
        from src.services import background_tasks as _bt
        _bt.create_task('old-task', user.id, kind='process',
                        label='Processing: Other goal')
        winner, existing, same = _bt.claim_pipeline_task(
            'new-task', user.id, kind='process',
            label='Processing: New stuff', match_label='Processing: New stuff')
        assert winner is False
        assert existing == 'old-task'
        assert same is False


def test_claim_first_pipeline_wins(bb_client):
    app, user = bb_client
    with app.app_context():
        from src.services import background_tasks as _bt
        winner, existing, same = _bt.claim_pipeline_task(
            'only-task', user.id, kind='generate', label='Lessons: X',
            match_label='Lessons: X')
        assert winner is True
        assert existing is None


def test_process_resubmits_follow_running_task(bb_client):
    app, user = bb_client
    client = app.test_client()
    _login(client)
    with app.app_context():
        from src.services import background_tasks as _bt
        _bt.create_task('old-task', user.id, kind='process',
                        label='Processing: Same goal')
    data = {
        'learning_goal': 'Same goal',
        'task_id': 'brand-new-task',
        'files': (io.BytesIO(b'Force equals mass times acceleration.'), 'physics.txt'),
    }
    resp = client.post('/process', data=data, content_type='multipart/form-data')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get('resumed') is True
    assert body.get('task_id') == 'old-task'


def test_process_different_goal_gets_busy_error(bb_client):
    app, user = bb_client
    client = app.test_client()
    _login(client)
    with app.app_context():
        from src.services import background_tasks as _bt
        _bt.create_task('old-task', user.id, kind='process',
                        label='Processing: Other goal')
    data = {
        'learning_goal': 'Entirely new stuff',
        'task_id': 'brand-new-task',
        'files': (io.BytesIO(b'Force equals mass times acceleration.'), 'physics.txt'),
    }
    resp = client.post('/process', data=data, content_type='multipart/form-data')
    assert resp.status_code == 429
    assert 'error' in resp.get_json()


# ── #4 Mascot prune + forget-me ────────────────────────────────────

def test_memory_prune_caps_per_user(bb_client, monkeypatch):
    app, user = bb_client
    with app.app_context():
        import src.services.mascot_memory as mm
        monkeypatch.setattr(mm, 'MAX_MEMORIES_PER_USER', 3)
        from src.models import MascotMemory
        for i in range(5):
            mm.store_memory(user.id, 'episodic', f'Event number {i}')
        rows = MascotMemory.query.filter_by(user_id=user.id).all()
        assert len(rows) == 3
        contents = [r.content for r in rows]
        assert 'Event number 4' in contents
        assert 'Event number 0' not in contents


def test_memory_coalesces_repeats(bb_client):
    app, user = bb_client
    with app.app_context():
        import src.services.mascot_memory as mm
        from src.models import MascotMemory
        mm.store_memory(user.id, 'semantic', 'Prefers Hard difficulty')
        mm.store_memory(user.id, 'semantic', 'Prefers Hard difficulty')
        assert MascotMemory.query.filter_by(user_id=user.id).count() == 1


def test_forget_memories_route(bb_client):
    app, user = bb_client
    client = app.test_client()
    _login(client)
    with app.app_context():
        from src.models import MascotMemory
        from src.services.mascot_memory import store_memory
        store_memory(user.id, 'episodic', 'Something to forget')
        assert MascotMemory.query.filter_by(user_id=user.id).count() == 1
    resp = client.post('/settings/forget-memories')
    assert resp.status_code == 302
    with app.app_context():
        from src.models import MascotMemory
        assert MascotMemory.query.filter_by(user_id=user.id).count() == 0
    body = client.get('/settings').get_data(as_text=True)
    assert 'Mascot Memory' in body


# ── Client resume hooks + theme ────────────────────────────────────

def test_client_resume_hooks_present():
    root = pathlib.Path(__file__).resolve().parents[1]
    upload = (root / 'src' / 'static' / 'js' / 'upload.js').read_text(encoding='utf-8')
    assert 'data.resumed' in upload
    progress = (root / 'src' / 'static' / 'js' / 'progress.js').read_text(encoding='utf-8')
    assert 'resp.resumed' in progress
    assert 'Generate Interactive Lessons' in progress
    css = (root / 'src' / 'static' / 'css' / 'retro.css').read_text(encoding='utf-8')
    assert '.weak-card' in css
    assert '.weak-badge' in css
