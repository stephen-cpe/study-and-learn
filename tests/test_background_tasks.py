"""
Tests for background tasks + bell (slice 6): durable BackgroundTask rows,
GET /tasks + POST /tasks/<id>/read, and process/generate route hooks.
"""
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import BackgroundTask, User


@pytest.fixture
def bt_app(monkeypatch):
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


def _seed_user(app, username='worker', **kwargs):
    with app.app_context():
        user = User(username=username, email=f'{username}@example.com', **kwargs)
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()
        return user.id


def test_task_helpers_never_raise(bt_app):
    from src.services import background_tasks as btsvc
    with bt_app.app_context():
        assert btsvc.list_tasks('nonexistent') == []
        assert btsvc.unread_count('nonexistent') == 0
        assert btsvc.mark_read('nope', 'nonexistent') is False
        btsvc.finish_task('nope')
        btsvc.fail_task('nope')


def test_create_finish_read_flow(bt_app):
    from src.services import background_tasks as btsvc
    user_id = _seed_user(bt_app)
    with bt_app.app_context():
        row = btsvc.create_task('t-1', user_id, kind='process', label='P')
        assert row is not None and row.status == 'running'
        assert btsvc.unread_count(user_id) == 0
        btsvc.finish_task('t-1', result_url='/results', label='Done')
        assert btsvc.unread_count(user_id) == 1
        tasks = btsvc.list_tasks(user_id)
        assert tasks[0]['result_url'] == '/results'
        assert btsvc.mark_read('t-1', user_id) is True
        assert btsvc.unread_count(user_id) == 0


def test_create_resets_existing_row(bt_app):
    from src.services import background_tasks as btsvc
    user_id = _seed_user(bt_app)
    with bt_app.app_context():
        btsvc.create_task('t-2', user_id, kind='process')
        btsvc.fail_task('t-2', error='boom')
        assert btsvc.unread_count(user_id) == 1
        btsvc.create_task('t-2', user_id, kind='generate')
        row = BackgroundTask.query.filter_by(task_id='t-2').first()
        assert row.status == 'running' and row.kind == 'generate'
        assert btsvc.unread_count(user_id) == 0


def test_tasks_endpoints(bt_app):
    user_id = _seed_user(bt_app)
    client = bt_app.test_client()
    _login(client, 'worker', 'pass')
    with bt_app.app_context():
        from src.services import background_tasks as btsvc
        btsvc.create_task('t-3', user_id, kind='generate', label='G')
        btsvc.finish_task('t-3', result_url='/lessons?path_id=x')
    resp = client.get('/tasks')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['unread'] == 1
    assert data['tasks'][0]['task_id'] == 't-3'
    resp = client.post('/tasks/t-3/read')
    assert resp.status_code == 200
    assert resp.get_json()['unread'] == 0
    assert client.post('/tasks/missing/read').status_code == 404


def test_tasks_require_login(bt_app):
    client = bt_app.test_client()
    assert client.get('/tasks').status_code in (302, 303, 401)


def test_tasks_isolated_per_user(bt_app):
    _seed_user(bt_app, username='alpha')
    _seed_user(bt_app, username='beta')
    client = bt_app.test_client()
    _login(client, 'alpha', 'pass')
    with bt_app.app_context():
        from src.services import background_tasks as btsvc
        beta = User.query.filter_by(username='beta').first()
        btsvc.create_task('t-4', beta.id, kind='process')
        btsvc.finish_task('t-4', result_url='/results')
    data = client.get('/tasks').get_json()
    assert data['tasks'] == [] and data['unread'] == 0
    assert client.post('/tasks/t-4/read').status_code == 404


def test_process_failure_records_failed_task(bt_app):
    import io
    _seed_user(bt_app, can_generate_lessons=True)
    client = bt_app.test_client()
    _login(client, 'worker', 'pass')
    # Valid goal + an invalid-type file passes validation (bell row gets
    # created) then fails mid-pipeline → row flips to failed.
    data = {
        'learning_goal': 'G',
        'task_id': 't-fail-1',
        'files': (io.BytesIO(b'evil'), 'evil.exe'),
    }
    resp = client.post('/process', data=data,
                       content_type='multipart/form-data')
    assert resp.status_code == 400
    with bt_app.app_context():
        row = BackgroundTask.query.filter_by(task_id='t-fail-1').first()
        assert row is not None and row.status == 'failed'


def test_sweep_orphaned_tasks(bt_app):
    from src.services import background_tasks as btsvc
    user_id = _seed_user(bt_app)
    with bt_app.app_context():
        btsvc.create_task('t-orphan', user_id, kind='process', label='Died')
        btsvc.create_task('t-done', user_id, kind='generate', label='Done')
        btsvc.finish_task('t-done', result_url='/lessons')
        assert btsvc.sweep_orphaned_tasks() == 1
        orphan = BackgroundTask.query.filter_by(task_id='t-orphan').first()
        assert orphan.status == 'failed'
        assert 'Interrupted' in (orphan.error or '')
        done = BackgroundTask.query.filter_by(task_id='t-done').first()
        assert done.status == 'ready'
        assert btsvc.sweep_orphaned_tasks() == 0


def test_dismiss_finished_row(bt_app):
    from src.services import background_tasks as btsvc
    user_id = _seed_user(bt_app)
    client = bt_app.test_client()
    _login(client, 'worker', 'pass')
    with bt_app.app_context():
        btsvc.create_task('t-d1', user_id, kind='process', label='Old')
        btsvc.finish_task('t-d1', result_url='/results')
        btsvc.create_task('t-live', user_id, kind='generate', label='Live')
    # Running rows are protected from dismissal.
    assert client.post('/tasks/t-live/dismiss').status_code == 404
    assert client.post('/tasks/t-d1/dismiss').status_code == 200
    with bt_app.app_context():
        assert BackgroundTask.query.filter_by(task_id='t-d1').first() is None
        assert BackgroundTask.query.filter_by(task_id='t-live').first() is not None


def test_clear_finished_keeps_running(bt_app):
    from src.services import background_tasks as btsvc
    user_id = _seed_user(bt_app)
    client = bt_app.test_client()
    _login(client, 'worker', 'pass')
    with bt_app.app_context():
        btsvc.create_task('t-c1', user_id, kind='process')
        btsvc.fail_task('t-c1', error='bad')
        btsvc.create_task('t-c2', user_id, kind='generate')
    resp = client.post('/tasks/clear')
    assert resp.status_code == 200
    assert resp.get_json()['cleared'] == 1
    with bt_app.app_context():
        assert BackgroundTask.query.filter_by(task_id='t-c1').first() is None
        assert BackgroundTask.query.filter_by(task_id='t-c2').first() is not None
    # Clearing is owner-scoped.
    assert client.post('/tasks/clear').get_json()['cleared'] == 0
