"""Tests for ordering/matching reorder UX + inline grade announcement."""
import json
import pathlib
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import StudyPath, User


@pytest.fixture
def dnd_client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('AI_MOCK', 'true')
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
            user = User(username='dndtester', email='dnd@example.com',
                        can_generate_lessons=True)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _seed_ordering_matching(app, user):
    from src.services.lesson_orchestrator import build_deck_layout
    slides = [{'type': 'title', 'title': 'T', 'subtitle': 'S'}]
    layout = build_deck_layout(slides, {})
    with app.app_context():
        path = StudyPath(
            user_id=user.id, title='P', learning_goal='G', status='active',
            content_data=json.dumps([{
                'index': 0, 'module_title': 'M1',
                'lesson': {'module_title': 'M1', 'slides': slides, 'deck_layout': layout},
                'quiz': {'questions': [
                    {'id': 'qo', 'type': 'ordering', 'prompt': 'Order.',
                     'items': ['A', 'B', 'C', 'D'], 'answer_order': [2, 0, 3, 1],
                     'explanation': 'E'},
                    {'id': 'qm', 'type': 'matching', 'prompt': 'Match.',
                     'lefts': ['L1', 'L2'], 'rights': ['R1', 'R2'],
                     'answer_indices': [1, 0], 'explanation': 'E'},
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


def test_ordering_rows_have_drag_buttons_badges_hidden_ranks(dnd_client):
    app, user = dnd_client
    path_id = _seed_ordering_matching(app, user)
    with app.test_client() as c:
        c.post('/login', data={'username': 'dndtester', 'password': 'pass'})
        body = c.get(f'/lessons/0?path_id={path_id}').get_data(as_text=True)
    assert 'q-drag-handle' in body
    assert 'q-position-badge' in body
    assert 'q-move-up' in body and 'q-move-down' in body
    # Hidden rank inputs preserve the deck-engine data contract.
    assert 'type="hidden"' in body
    assert 'q-order-select' in body
    assert 'data-item="0"' in body
    # No empty "#" placeholder anymore; ranks pre-numbered.
    assert '>#' not in body
    assert 'Select match...' not in body


def test_matching_rows_have_swap_buttons_and_preselected(dnd_client):
    app, user = dnd_client
    path_id = _seed_ordering_matching(app, user)
    with app.test_client() as c:
        c.post('/login', data={'username': 'dndtester', 'password': 'pass'})
        body = c.get(f'/lessons/0?path_id={path_id}').get_data(as_text=True)
    assert 'q-swap-up' in body and 'q-swap-down' in body
    assert 'q-matching-select' in body
    assert 'selected' in body


def test_shuffle_guarantees_nontrivial_order():
    import random

    from src.services.quiz_generator import _shuffle_sequence
    random.seed(20260916)
    for _ in range(100):
        disp, new_correct = _shuffle_sequence(['A', 'B', 'C', 'D'], [0, 1, 2, 3])
        assert new_correct != [0, 1, 2, 3]
        assert all(new_correct[i] != i for i in range(4))


def test_deck_js_has_reorder_and_inline_announcement():
    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / 'src' / 'static' / 'js' / 'deck-page.js').read_text(encoding='utf-8')
    assert 'initOrderingControls' in js
    assert 'initMatchingControls' in js
    assert 'swapMatchingRows' in js
    assert '__ttsSuppressNext' in js
    # Inline fast-path: grade-provided audio_url plays without a fetch.
    assert 'data.announcement.audio_url' in js


def test_deck_js_has_touch_drag_without_touching_mouse_path():
    root = pathlib.Path(__file__).resolve().parents[1]
    js = (root / 'src' / 'static' / 'js' / 'deck-page.js').read_text(encoding='utf-8')
    # Touch layer is additive: mouse HTML5 DnD stays intact.
    assert 'enableTouchDrag' in js
    assert 'pointerdown' in js
    assert 'touchstart' in js  # fallback for browsers without PointerEvent
    assert 'pointercancel' in js
    assert "e.pointerType === 'mouse'" in js
    assert 'dragstart' in js  # mouse path untouched
    assert 'dragover' in js


def test_deck_css_has_coarse_pointer_touch_targets():
    root = pathlib.Path(__file__).resolve().parents[1]
    css = (root / 'src' / 'static' / 'css' / 'deck-components.css').read_text(encoding='utf-8')
    assert 'pointer: coarse' in css
    assert 'touch-action: none' in css  # handle-only: page scroll elsewhere unaffected
