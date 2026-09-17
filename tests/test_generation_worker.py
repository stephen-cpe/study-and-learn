"""Tests for the background lesson-generation worker (#5).

The route runs inline under TESTING (existing suite covers that
contract); these tests cover the worker itself: success persistence,
threaded spawn, contained failure, and the new client fast-path hooks.
"""
import json
import pathlib
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, User


@pytest.fixture
def gen_client(monkeypatch):
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
            user = User(username='genworker', email='gw@example.com',
                        can_generate_lessons=True, tts_enabled=False,
                        tts_speaker='Ava', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _shell_path(app, user):
    with app.app_context():
        from src.repositories.lesson_repo import create_study_path
        path = create_study_path(
            user, 'Async Path', 'Learn async',
            extracted_texts=['Async generation grounds lessons in this text.'],
            modules=[{'title': 'Intro Mod'}, {'title': 'Next Mod'}],
            summary='S', relevance_result={})
        return path.id


def _payload(modules=2):
    mods = [{'title': f'Mod {i + 1}'} for i in range(modules)]
    return {
        'learning_goal': 'Learn async',
        'study_title': 'Async Path',
        'modules': mods,
        'existing_lessons': [],
        'extracted_texts': ['Async generation grounds lessons in this text.'],
        'file_hashes': [],
        'file_names': [],
        'content_digest': '',
        'tts_enabled': False,
        'tts_speaker': 'Ava',
        'difficulty': 'Normal',
        'display_name': 'genworker',
    }


def test_run_generation_persists_lessons_and_completes(gen_client):
    app, user = gen_client
    path_id = _shell_path(app, user)
    with app.app_context():
        from src.services import background_tasks as _bt
        from src.services import progress_tracker
        from src.services.generation_worker import run_generation_for_path
        progress_tracker.create_task(task_id='gen-task-1', display_name='genworker')
        _bt.create_task('gen-task-1', user.id, kind='generate', label='t')
        result = run_generation_for_path(
            app, user.id, path_id, _payload(), 'gen-task-1')
    assert result['ok'] is True
    assert result['modules'] == 2
    with app.app_context():
        path = StudyPath.query.get(path_id)
        lessons = json.loads(path.content_data)
        assert len(lessons) == 2
        assert lessons[0]['module_title'] == 'Mod 1'
        assert path.generation_completed_at is not None
        assert path.extracted_texts is None
        from src.services.background_tasks import list_tasks
        rows = [t for t in list_tasks(user.id) if t['task_id'] == 'gen-task-1']
        assert rows and rows[0]['status'] == 'ready'
        assert f'path_id={path_id}' in (rows[0]['result_url'] or '')


def test_spawn_runs_thread_to_completion(gen_client):
    app, user = gen_client
    path_id = _shell_path(app, user)
    with app.app_context():
        from src.services import background_tasks as _bt
        from src.services import progress_tracker
        from src.services.generation_worker import spawn_generation_background_task
        progress_tracker.create_task(task_id='gen-task-2', display_name='genworker')
        _bt.create_task('gen-task-2', user.id, kind='generate', label='t')
        thread = spawn_generation_background_task(
            app, user.id, path_id, _payload(modules=1), 'gen-task-2')
        thread.join(timeout=90)
        assert not thread.is_alive()
        path = StudyPath.query.get(path_id)
        assert json.loads(path.content_data)[0]['module_title'] == 'Mod 1'
        assert path.generation_completed_at is not None


def test_worker_failure_is_contained(gen_client, monkeypatch):
    app, user = gen_client
    path_id = _shell_path(app, user)

    def boom(*a, **k):
        raise RuntimeError('llm down')

    monkeypatch.setattr(
        'src.services.lesson_orchestrator.build_module_artifacts', boom)
    with app.app_context():
        from src.services import background_tasks as _bt
        from src.services import progress_tracker
        from src.services.generation_worker import run_generation_for_path
        progress_tracker.create_task(task_id='gen-task-3', display_name='genworker')
        _bt.create_task('gen-task-3', user.id, kind='generate', label='t')
        result = run_generation_for_path(
            app, user.id, path_id, _payload(modules=1), 'gen-task-3')
    assert result['ok'] is False
    with app.app_context():
        from src.services.background_tasks import list_tasks
        rows = [t for t in list_tasks(user.id) if t['task_id'] == 'gen-task-3']
        assert rows and rows[0]['status'] == 'failed'
        # Completion flag stays unset so the client shows the error
        # instead of landing on an empty lessons page.
        assert StudyPath.query.get(path_id).generation_completed_at is None


def test_client_handles_accepted_and_failure():
    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / 'src' / 'static' / 'js' / 'progress.js').read_text(encoding='utf-8')
    assert 'resp.accepted' in js
    assert 'resolvedPathId = resp.path_id' in js
    assert 'task_status' in js
    assert '/lessons?path_id=' in js
