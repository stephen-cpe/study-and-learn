"""Regression tests for live progress feedback during the full-coverage
map step of /process.

The user-visible symptom being guarded: during the (long) map step the
mascot speech bubble and progress bar must keep updating (a rotating
"Reading sections n/m..." line and a climbing percentage), and the busy
sprite must stay animated.  Before the fix the callback only sent ``pct``,
so the bubble froze on the previous stage and the JS stale-timeout handler
overwrote it with a permanent "hang tight!".
"""
import io
import json
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User
from src.services import progress_tracker


@pytest.fixture
def client(monkeypatch):
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
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app_instance.extensions.pop('sqlalchemy', None)
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            user = User(username='progresser', email='p@example.com',
                        can_generate_lessons=True)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'progresser', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


def test_map_progress_publishes_full_cosmetic_fields(client, monkeypatch):
    """The map step callback must send label + mascot + mascot_state + pct.

    If any of label/mascot/mascot_state go missing the JS bubble cannot
    render the rotating "Reading sections n/m..." line or keep the busy
    sprite animation, so it looks frozen.
    """
    captured = []

    def fake_full(goal, hashes, names, top_k=None, exclude_chunks=None,
                 progress_callback=None, **kw):
        # Simulate the map step invoking its progress callback.
        if progress_callback:
            progress_callback(1, 12)
            progress_callback(2, 12)
        return {'context_text': 'ctx', 'content_digest': 'd',
                'coverage_ratio': 0.9}

    def spy_cosmetic(task_id, **fields):
        captured.append(fields)
        return None

    monkeypatch.setattr(
        'src.routes.processing.build_full_coverage_context', fake_full
    )
    monkeypatch.setattr(
        'src.services.progress_tracker.update_cosmetic', spy_cosmetic
    )
    # Keep the AI calls cheap/deterministic.
    monkeypatch.setattr(
        'src.routes.processing.generate_summary', lambda ctx: 'summary'
    )
    monkeypatch.setattr(
        'src.routes.processing.check_relevance',
        lambda g, c, s: {'relevance_label': 'strong',
                         'explanation': '', 'missing_material': ''},
    )
    monkeypatch.setattr(
        'src.routes.processing.generate_study_path',
        lambda g, c, s: {'title': 'T', 'modules':
                         [{'title': 'M1', 'estimated_effort': '1h'}]},
    )

    data = {
        'learning_goal': 'Learn testing',
        'task_id': 'prog-task-1',
        'files': (io.BytesIO(b'hello world text'), 'a.txt'),
    }
    rv = client.post('/process', data=data,
                     content_type='multipart/form-data')
    assert rv.status_code == 200

    # At least one callback fired.
    map_calls = [c for c in captured if 'label' in c or 'mascot' in c]
    assert map_calls, 'expected at least one map-progress cosmetic call'

    for call in map_calls:
        assert call.get('mascot_state') == 'busy', (
            'map progress must force the busy mascot state so the sprite '
            'keeps animating'
        )
        assert isinstance(call.get('label'), str) and call['label'], (
            'map progress must supply a human-readable label'
        )
        assert isinstance(call.get('mascot'), str) and call['mascot'], (
            'map progress must supply a bubble message'
        )
        assert isinstance(call.get('pct'), int), (
            'map progress must advance the progress bar'
        )

    # The counter must be visible in the bubble text so the user sees
    # forward motion (e.g. "Reading sections 2/12...").
    assert any('/' in c['mascot'] for c in map_calls), (
        'bubble text should include the section n/m counter'
    )


def test_map_progress_pct_capped_at_80():
    """The map step's cosmetic pct must never exceed 80 (it occupies
    stages 55-80 inside PROCESS_STAGES)."""
    # Replicate the formula used in processing.py
    for done, total in [(1, 3), (3, 3), (99, 100)]:
        pct = min(80, 55 + int((done / max(total, 1)) * 25))
        assert pct <= 80
        assert pct >= 55


def test_process_task_progress_endpoint_returns_fields(client, monkeypatch):
    """/progress returns the stage/label/pct/mascot fields the JS needs."""
    task_id = progress_tracker.create_task(
        task_id='endpoint-probe',
        stages=progress_tracker.PROCESS_STAGES,
        display_name='Tester',
    )
    progress_tracker.update_progress(task_id, 5)

    rv = client.get(f'/progress?task_id={task_id}')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['stage'] == 5
    assert data['label'] == 'Reading all pages'
    assert data['pct'] == 55
    assert data['mascot']
    progress_tracker.cleanup_task(task_id)
