"""
Tests for the lesson-deck UI consistency — specifically that the cloze_dropdown
checkpoint Quick Check uses the same Continue button (class, label, default
visibility) as mcq / true_false checkpoints.

Regression: previously cloze_dropdown rendered a separate `<button
class="checkpoint-check-btn">Check Answer</button>` with a different style
(outlined / transparent) and was always visible. This test pins the
consistent behavior:

  * The button uses the shared `.btn-submit-quiz` class.
  * The label is "Continue" (not "Check Answer").
  * The button is hidden by default (`display: none`) and revealed once the
    learner selects a value from the dropdown.
  * No `.checkpoint-check-btn` is rendered for cloze_dropdown checkpoints.
"""
import io
import json
import re
import tempfile

import pytest
from cachelib import FileSystemCache
from unittest.mock import patch

from src import create_app, db
from src.models import User
from src.repositories.lesson_repo import save_lessons


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn',
    )
    monkeypatch.setenv('AI_MOCK', 'true')

    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config.update({
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
        Session(app)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.extensions.pop('sqlalchemy', None)
        db.init_app(app)
        with app.app_context():
            db.create_all()
            user = User(
                username='clozeui',
                email='clozeui@example.com',
                can_generate_lessons=True,
            )
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()

            # Persist a study path with one module that has a cloze_dropdown
            # checkpoint at slide 0.
            # Task 4: the lesson dict must include a 'deck_layout' entry
            # that the template iterates over. The orchestrator builds
            # this in production; in this test we replicate the structure.
            slides = [{
                'type': 'content',
                'heading': 'Intro',
                'bullets': ['Topic A', 'Topic B'],
            }]
            checkpoints = {
                '0': {
                    'type': 'cloze_dropdown',
                    'prompt': 'The capital of France is ___.',
                    'options': ['Paris', 'Berlin', 'Madrid', 'London'],
                    'answer_index': 0,
                    'explanation': 'Paris is the capital.',
                },
            }
            # Build the canonical deck layout matching build_deck_layout().
            deck_layout = []
            di = 0
            for ci, s in enumerate(slides):
                deck_layout.append({
                    'deck_index': di, 'type': 'content', 'content_index': ci,
                    'slide': s, 'checkpoint': None, 'is_quiz': False, 'is_results': False,
                })
                di += 1
                cp = checkpoints.get(str(ci))
                if cp:
                    deck_layout.append({
                        'deck_index': di, 'type': 'checkpoint', 'content_index': ci,
                        'slide': None, 'checkpoint': cp, 'is_quiz': False, 'is_results': False,
                    })
                    di += 1
            deck_layout.append({
                'deck_index': di, 'type': 'quiz', 'content_index': None,
                'slide': None, 'checkpoint': None, 'is_quiz': True, 'is_results': False,
            })
            di += 1
            deck_layout.append({
                'deck_index': di, 'type': 'results', 'content_index': None,
                'slide': None, 'checkpoint': None, 'is_quiz': False, 'is_results': True,
            })

            save_lessons(
                user=user,
                lessons=[{
                    'module_title': 'Module 1',
                    'module_index': 0,
                    'lesson': {
                        'slides': slides,
                        'deck_layout': deck_layout,
                    },
                    'quiz': {
                        'questions': [
                            {
                                'id': 'q1',
                                'type': 'mcq',
                                'prompt': 'Pick one.',
                                'options': ['A', 'B', 'C', 'D'],
                                'answer_index': 0,
                                'explanation': 'A is correct.',
                            },
                        ],
                    },
                    'checkpoints': checkpoints,
                }],
                learning_goal='Learn geography',
                path_id=None,
            )

            with app.test_client() as c:
                c.post('/login', data={'username': 'clozeui', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


# ── Helpers ───────────────────────────────────────────────────────────────


def _extract_checkpoint_block(html: str, deck_index: int) -> str:
    """Return the raw HTML chunk for the checkpoint-slide at ``deck_index``.

    The deck layout was re-aligned in Task 4 so every <section class="slide">
    carries a unique ``data-deck-index``. The cloze-continue-button test
    only cares about the FIRST checkpoint in the deck (which is the only
    one in the test fixture) — we search by class + the next data-deck-index
    attribute that follows the class declaration.
    """
    pattern = (
        r'<section[^>]*class="[^"]*checkpoint-slide[^"]*"[^>]*'
        r'data-deck-index="\d+"[^>]*>.*?</section>'
    )
    m = re.search(pattern, html, flags=re.DOTALL)
    assert m, f'checkpoint-slide (deck_index={deck_index}) not found'
    return m.group(0)


# ── Tests ─────────────────────────────────────────────────────────────────


def test_cloze_checkpoint_renders_continue_button(client):
    """Cloze checkpoint must use the shared `.btn-submit-quiz` Continue button."""
    response = client.get('/lessons/0')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    block = _extract_checkpoint_block(html, deck_index=0)
    assert block, 'Cloze checkpoint slide not found in rendered deck'

    # The shared button class is present.
    assert 'btn-submit-quiz' in block, (
        'Cloze checkpoint must use the shared .btn-submit-quiz class so the '
        'Continue button matches mcq/true_false styling. Found block:\n' + block
    )

    # The label is "Continue" — not "Check Answer".
    assert '>Continue<' in block, (
        'Cloze checkpoint Continue button must be labelled "Continue". '
        'Found block:\n' + block
    )
    assert 'Check Answer' not in block, (
        'Cloze checkpoint must NOT render the legacy "Check Answer" label. '
        'Found block:\n' + block
    )


def test_cloze_checkpoint_does_not_render_legacy_check_button(client):
    """The deprecated `.checkpoint-check-btn` element must not be present
    for cloze_dropdown checkpoints. It is replaced by the shared Continue
    button and the change-event handler in deck-engine.js / deck-page.js."""
    response = client.get('/lessons/0')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    block = _extract_checkpoint_block(html, deck_index=0)
    assert 'checkpoint-check-btn' not in block, (
        'Legacy .checkpoint-check-btn must not be rendered for cloze_dropdown. '
        'Found block:\n' + block
    )


def test_cloze_checkpoint_continue_button_hidden_by_default(client):
    """The Continue button must start hidden (`display: none`) and be revealed
    after the learner picks a value — same as the mcq/true_false path."""
    response = client.get('/lessons/0')
    assert response.status_code == 200
    html = response.data.decode('utf-8')

    block = _extract_checkpoint_block(html, deck_index=0)

    # The shared Continue button is rendered with `display: none` initially.
    m = re.search(
        r'<button[^>]*class="[^"]*btn-submit-quiz[^"]*"[^>]*>',
        block,
    )
    assert m, 'Continue button not found in cloze checkpoint block'
    button_tag = m.group(0)
    assert 'display: none' in button_tag, (
        'Cloze checkpoint Continue button must be hidden by default; got:\n'
        + button_tag
    )
