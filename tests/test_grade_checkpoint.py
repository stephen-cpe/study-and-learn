"""
Regression tests for the checkpoint-vs-final-quiz grading distinction.

Background
----------
The deck calls POST /lessons/<i>/grade twice:
  (a) Per-checkpoint formative grades — `answers` is empty, only
      `checkpoint_answers` carries the single checkpoint being answered.
  (b) The final-quiz submission — `answers` carries the per-question
      quiz answers (plus any accumulated checkpoint_answers).

Previously the route flipped completed=True/score/passed on EVERY grade
POST. A user who exited mid-lesson (after 1-2 checkpoints) returned to
the lessons page and saw "25% — Retry Available" + "Retake Lesson",
which then regenerated the module and reset deck_position=0, discarding
their progress.

The fix: only the final-quiz submission (quiz answers present, or a
lesson with zero quiz questions) persists completed/score/passed.
Checkpoint-only POSTs return per-checkpoint feedback without mutating
lesson status.

These tests also cover the lessons.html UI states:
  - In Progress + Resume Lesson  (not completed, deck_position > 0)
  - Retry Available + Retake Lesson (completed, not passed)
  - Passed + Review Lesson (completed, passed)
  - Start Lesson (not completed, deck_position == 0)
"""
import json
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User, StudyPath
from src.repositories.lesson_repo import get_lessons


@pytest.fixture
def grade_client(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://test:test@localhost:5432/test'
    )
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
                username='gradetester', email='grade@example.com',
                can_generate_lessons=True, lesson_difficulty='Normal',
            )
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            yield app, user
            db.session.remove()
            db.drop_all()


def _seed_path(app, user, module_overrides=None, num_modules=1):
    """Seed a StudyPath with lessons. ``module_overrides`` is a list of
    dicts whose keys are merged into the corresponding module's lesson dict
    (e.g. {'completed': True, 'passed': False, 'score': 40,
    'deck_position': 5})."""
    module_overrides = module_overrides or [{}]
    with app.app_context():
        lessons = []
        for i in range(num_modules):
            base = {
                'index': i,
                'module_title': f'Module {i + 1}',
                'estimated_effort': '30 min',
                'lesson': {
                    'module_title': f'Module {i + 1}',
                    'slides': [
                        {'type': 'title', 'title': f'Title {i}',
                         'subtitle': ''},
                        {'type': 'content', 'heading': 'H',
                         'bullets': ['a', 'b']},
                    ],
                },
                'quiz': {
                    'questions': [
                        {'id': 'q1', 'type': 'mcq', 'prompt': 'P?',
                         'options': ['A', 'B', 'C', 'D'],
                         'answer_index': 0, 'explanation': 'E'}
                    ]
                },
                'checkpoints': {
                    '1': {'type': 'mcq', 'prompt': 'CP1?',
                          'options': ['A', 'B', 'C', 'D'],
                          'answer_index': 1, 'explanation': 'CE1'},
                    '3': {'type': 'true_false', 'prompt': 'CP2?',
                          'answer': 'true', 'explanation': 'CE2'},
                },
                'sources': [],
                'difficulty': 'Normal',
                'tts_enabled': False,
                'tts_speaker': 'Ava',
                'completed': False,
                'score': None,
                'passed': False,
                'deck_position': 0,
            }
            base.update(module_overrides[i] if i < len(module_overrides)
                        else {})
            lessons.append(base)
        path = StudyPath(
            user_id=user.id, title='Grade Path',
            learning_goal='Learn X', status='active',
            content_data=json.dumps(lessons),
        )
        db.session.add(path)
        db.session.commit()
        return path.id


# ── grade_lesson: checkpoint-only vs final-quiz ────────────────────────────


class TestGradeCheckpointVsFinalQuiz:
    def test_checkpoint_only_does_not_mark_completed(self, grade_client):
        """A per-checkpoint POST (answers empty) must NOT flip
        completed/score/passed. Regression for the 'exit mid-lesson →
        Retry Available → retake resets progress' bug."""
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            resp = c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    'answers': [],
                    'checkpoint_answers': {'1': 1},
                }),
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        # Per-checkpoint feedback is still returned for the deck UI.
        assert 'checkpoint_results' in data
        assert any(str(r['slide_index']) == '1' for r in
                   data['checkpoint_results'])
        # The lesson status must NOT have been persisted.
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0]['completed'] is False, (
                "Checkpoint-only grade must not mark the lesson completed — "
                "that was the root cause of the premature 'Retry Available' "
                "badge and the retake-that-discards-progress bug."
            )
            assert lessons[0]['score'] is None
            assert lessons[0]['passed'] is False

    def test_checkpoint_only_does_not_overwrite_prior_status(self, grade_client):
        """If a lesson was already passed, a stray checkpoint-only POST
        must not wipe that status."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': True, 'passed': True, 'score': 100,
        }])
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    'answers': [],
                    'checkpoint_answers': {'1': 0},
                }),
                content_type='application/json',
            )
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0]['completed'] is True
            assert lessons[0]['passed'] is True
            assert lessons[0]['score'] == 100

    def test_final_quiz_submission_marks_completed(self, grade_client):
        """The final-quiz POST (quiz answers present) must persist
        completed/score/passed — this is the legitimate completion path."""
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            resp = c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    # q1 is mcq with answer_index 0 → correct
                    'answers': [0],
                    'checkpoint_answers': {'1': 1, '3': 'true'},
                }),
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['score'] == 100  # 1 quiz + 2 checkpoints, all correct
        assert data['passed'] is True
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0]['completed'] is True
            assert lessons[0]['passed'] is True
            assert lessons[0]['score'] == 100

    def test_final_quiz_failure_marks_completed_not_passed(self, grade_client):
        """A failed final quiz must set completed=True, passed=False so the
        'Retry Available' + 'Retake Lesson' UI appears — the correct
        semantic for a genuinely failed lesson."""
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            # Wrong quiz answer + wrong checkpoints → 0/3 = 0%
            resp = c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    'answers': [3],  # wrong (answer_index is 0)
                    'checkpoint_answers': {'1': 0, '3': 'false'},
                }),
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['passed'] is False
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0]['completed'] is True
            assert lessons[0]['passed'] is False


# ── lessons.html UI states ─────────────────────────────────────────────────


class TestLessonsPageUIStates:
    def _login_and_view(self, c, path_id):
        c.post('/login', data={'username': 'gradetester', 'password': 'pass'})
        return c.get(f'/lessons?path_id={path_id}')

    @staticmethod
    def _cards_only(body):
        """Return only the lesson-card markup, stripping inline <script>
        blocks. The lessons page includes a retake-handler script whose
        literal strings ('Retake Lesson', '.lesson-retake-btn') would
        otherwise false-positive against whole-page substring checks.
        The cards live inside <div class="lessons-grid">...</div>."""
        import re
        m = re.search(
            r'<div class="lessons-grid">(.*?)</div>\s*<div class="action-buttons',
            body, flags=re.DOTALL,
        )
        return m.group(1) if m else body

    def test_in_progress_lesson_shows_resume_and_in_progress_badge(
            self, grade_client):
        """A not-completed lesson with deck_position > 0 must show
        'Resume Lesson' (not 'Retake Lesson') and an 'In Progress' badge
        (not 'Retry Available')."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': False, 'passed': False, 'score': None,
            'deck_position': 4,
        }])
        with app.test_client() as c:
            body = self._login_and_view(c, path_id).get_data(as_text=True)
        cards = self._cards_only(body)
        assert 'Resume Lesson' in cards, (
            "An in-progress lesson (deck_position > 0, not completed) must "
            "offer 'Resume Lesson', not 'Retake Lesson'."
        )
        assert 'In Progress' in cards, (
            "An in-progress lesson must show the 'In Progress' badge, not "
            "'Retry Available'."
        )
        assert 'Retry Available' not in cards
        assert 'lesson-retake-btn' not in cards

    def test_failed_lesson_still_shows_retake(self, grade_client):
        """Guard against over-correction: a genuinely failed lesson
        (completed=True, passed=False) must still show 'Retake Lesson'
        and 'Retry Available'."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': True, 'passed': False, 'score': 40,
            'deck_position': 0,
        }])
        with app.test_client() as c:
            body = self._login_and_view(c, path_id).get_data(as_text=True)
        cards = self._cards_only(body)
        assert 'Retake Lesson' in cards
        assert 'Retry Available' in cards
        assert 'Resume Lesson' not in cards
        assert 'In Progress' not in cards

    def test_failed_lesson_card_renders_retake_button_not_deck_link(
            self, grade_client):
        """Regression: a failed-lesson card must render a retake TRIGGER
        (button posting to /retake) — NOT a plain <a> linking to the deck
        route. The plain link dropped users onto the stale final-quiz
        slide instead of regenerating the lesson.

        The card must carry the .lesson-retake-btn class with the
        module_index + path_id data attributes the inline JS binds to,
        and the page must include the inline handler that POSTs to
        /lessons/<i>/retake. Crucially the card must NOT link to
        /lessons/<i>?path_id=... (the deck route) for the failed module.
        """
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': True, 'passed': False, 'score': 40,
            'deck_position': 5,
        }])
        with app.test_client() as c:
            body = self._login_and_view(c, path_id).get_data(as_text=True)
        cards = self._cards_only(body)
        # The retake trigger button is present with the right wiring.
        assert 'lesson-retake-btn' in cards, (
            "Failed-lesson card must render a .lesson-retake-btn button."
        )
        assert 'data-module-index="0"' in cards
        assert f'data-path-id="{path_id}"' in cards
        # The inline handler that POSTs to /retake is on the page.
        assert "/lessons/' + mIdx + '/retake" in body, (
            "Inline retake handler must POST to /lessons/<i>/retake."
        )
        assert "Regenerating..." in body, (
            "The retake button must show 'Regenerating...' while the POST "
            "is in flight, matching the in-deck retake button."
        )
        # The failed-lesson card must NOT link to the deck route (which
        # would land the user on the stale final-quiz slide). The deck
        # link href uses url_for('main.lesson_deck', module_index=0, ...).
        assert 'lesson-start-btn' not in cards, (
            "A failed-lesson card must not render a .lesson-start-btn deck "
            "link — it must use the retake POST button instead."
        )

    def test_retake_post_from_card_regenerates_and_resets(
            self, grade_client):
        """End-to-end: hitting the retake POST (as the card's inline
        handler does) regenerates the lesson, resets deck_position to 0,
        and returns a redirect to the fresh deck — not the stale final
        quiz."""
        from unittest.mock import patch
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': True, 'passed': False, 'score': 40,
            'deck_position': 9,
        }])
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            with patch('src.services.quiz_generator.call_ollama') as mq, \
                    patch('src.services.lesson_generator.call_ollama') as ml:
                mq.return_value = json.dumps({
                    'questions': [{
                        'id': 'q_new', 'type': 'mcq', 'prompt': 'N?',
                        'options': ['A', 'B', 'C', 'D'],
                        'answer_index': 0, 'explanation': 'E',
                    }]
                })
                ml.return_value = json.dumps({
                    'module_title': 'Module 1',
                    'slides': [
                        {'type': 'title', 'title': 'T', 'subtitle': ''},
                    ],
                })
                resp = c.post(
                    f'/lessons/0/retake?path_id={path_id}',
                    data=json.dumps({'path_id': path_id}),
                    content_type='application/json',
                )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'redirect' in data
        assert '/lessons/0' in data['redirect']
        assert f'path_id={path_id}' in data['redirect']
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0]['deck_position'] == 0, (
                "Retake must reset deck_position so the user starts from "
                "slide 0, not the stale final-quiz position."
            )
            assert lessons[0]['completed'] is False
            assert lessons[0]['passed'] is False
            assert lessons[0]['score'] is None

    def test_passed_lesson_shows_review(self, grade_client):
        """A passed lesson must show 'Review Lesson' and 'Passed'."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': True, 'passed': True, 'score': 100,
            'deck_position': 0,
        }])
        with app.test_client() as c:
            body = self._login_and_view(c, path_id).get_data(as_text=True)
        cards = self._cards_only(body)
        assert 'Review Lesson' in cards
        assert 'Passed' in cards
        assert 'lesson-retake-btn' not in cards
        assert 'Resume Lesson' not in cards

    def test_fresh_lesson_shows_start(self, grade_client):
        """A fresh, never-started lesson (deck_position == 0, not completed)
        must show 'Start Lesson'."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': False, 'passed': False, 'score': None,
            'deck_position': 0,
        }])
        with app.test_client() as c:
            body = self._login_and_view(c, path_id).get_data(as_text=True)
        cards = self._cards_only(body)
        assert 'Start Lesson' in cards
        assert 'Resume Lesson' not in cards
        assert 'lesson-retake-btn' not in cards
        assert 'In Progress' not in cards


# ── Resume after checkpoints: persisted answers credited on final quiz ──────


class TestResumeAfterCheckpointsGrading:
    """Regression: a user who answers checkpoints in one session, exits, and
    resumes later to take the final quiz must be credited for the
    checkpoints they already answered — otherwise a perfect quiz score
    would be dragged below the pass threshold (e.g. 5/9 ≈ 56%)."""

    def test_persisted_checkpoints_credited_on_resume_final_quiz(
            self, grade_client):
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            # Session 1: answer both checkpoints correctly, then exit
            # (no final quiz). Each is a checkpoint-only POST.
            c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({'answers': [],
                                 'checkpoint_answers': {'1': 1}}),
                content_type='application/json',
            )
            c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({'answers': [],
                                 'checkpoint_answers': {'3': 'true'}}),
                content_type='application/json',
            )

        # The lesson must NOT be marked completed, and the checkpoint
        # answers must be persisted onto the lesson dict.
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0]['completed'] is False
            persisted = lessons[0].get('checkpoint_user_answers', {})
            assert persisted.get('1') == 1
            assert persisted.get('3') == 'true'

        # Session 2: resume and submit the final quiz with correct
        # answers, sending NO checkpoint_answers (the JS map is empty on
        # a fresh page load — the server must fall back to persisted).
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            resp = c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    'answers': [0],
                    'checkpoint_answers': {},
                }),
                content_type='application/json',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['score'] == 100, (
            f"Resumed final quiz must credit persisted checkpoint answers; "
            f"got {data['score']}% (expected 100%)."
        )
        assert data['passed'] is True

    def test_fresh_quiz_submission_still_works_without_persisted(
            self, grade_client):
        """Single-session flow (no exit) must be unaffected: submitting the
        final quiz with full checkpoint_answers yields 100% even when no
        persisted map exists."""
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            resp = c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    'answers': [0],
                    'checkpoint_answers': {'1': 1, '3': 'true'},
                }),
                content_type='application/json',
            )
        data = resp.get_json()
        assert data['score'] == 100
        assert data['passed'] is True

    def test_reanswered_checkpoint_overrides_persisted(self, grade_client):
        """On resume, a freshly-submitted checkpoint answer must override the
        persisted one (the user changed their mind)."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            # Persist a WRONG answer for checkpoint '1' (correct is 1).
            'checkpoint_user_answers': {'1': 0, '3': 'true'},
        }])
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            # Resume and re-answer checkpoint '1' correctly, plus the quiz.
            resp = c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({
                    'answers': [0],
                    'checkpoint_answers': {'1': 1},
                }),
                content_type='application/json',
            )
        data = resp.get_json()
        # Fresh '1':1 (correct) overrides persisted '1':0 (wrong); '3'
        # comes from the persisted 'true' (correct). All correct → 100%.
        assert data['score'] == 100, (
            f"Fresh checkpoint answer must override persisted; got "
            f"{data['score']}%."
        )
        assert data['passed'] is True

    def test_checkpoint_only_post_persists_answers(self, grade_client):
        """A checkpoint-only POST must persist the answered checkpoint into
        checkpoint_user_answers on the lesson dict (this is what makes the
        resume flow work)."""
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            c.post(
                f'/lessons/0/grade?path_id={path_id}',
                data=json.dumps({'answers': [],
                                 'checkpoint_answers': {'1': 1}}),
                content_type='application/json',
            )
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert lessons[0].get('checkpoint_user_answers',
                                  {}) == {'1': 1}

    def test_retake_clears_persisted_checkpoint_answers(self, grade_client):
        """Retake must clear checkpoint_user_answers so the retaken module
        starts with a clean slate (regenerated checkpoints have new
        prompts/options)."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'completed': True, 'passed': False, 'score': 40,
            'checkpoint_user_answers': {'1': 1, '3': 'true'},
        }])
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            from unittest.mock import patch
            with patch('src.services.quiz_generator.call_ollama') as mq, \
                    patch('src.services.lesson_generator.call_ollama') as ml:
                mq.return_value = json.dumps({
                    'questions': [{
                        'id': 'q_new', 'type': 'mcq', 'prompt': 'N?',
                        'options': ['A', 'B', 'C', 'D'],
                        'answer_index': 0, 'explanation': 'E',
                    }]
                })
                ml.return_value = json.dumps({
                    'module_title': 'Module 1',
                    'slides': [
                        {'type': 'title', 'title': 'T', 'subtitle': ''},
                    ],
                })
                c.post(
                    f'/lessons/0/retake?path_id={path_id}',
                    data=json.dumps({'path_id': path_id}),
                    content_type='application/json',
                )
        with app.app_context():
            lessons = get_lessons(user, path_id=path_id)
            assert 'checkpoint_user_answers' not in lessons[0], (
                "Retake must clear persisted checkpoint answers."
            )
            assert lessons[0]['deck_position'] == 0
            assert lessons[0]['completed'] is False


# ── lesson_deck.html emits persisted checkpoint answers ────────────────────


class TestDeckEmitsPersistedCheckpointAnswers:
    def test_deck_container_carries_data_attribute(self, grade_client):
        """The deck container must emit data-checkpoint-answers so the JS
        can hydrate the in-memory checkpointAnswers map on resume."""
        app, user = grade_client
        path_id = _seed_path(app, user, module_overrides=[{
            'deck_position': 4,
            'checkpoint_user_answers': {'1': 1, '3': 'true'},
        }])
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            body = c.get(f'/lessons/0?path_id={path_id}').get_data(
                as_text=True)
        assert 'data-checkpoint-answers=' in body, (
            "Deck container must carry data-checkpoint-answers so the JS "
            "can restore persisted checkpoint answers on resume."
        )

    def test_deck_container_has_empty_map_when_none(self, grade_client):
        """When no checkpoints have been answered, the attribute should
        still be present (empty object) so the JS hydration is a no-op
        rather than a missing-attribute error."""
        app, user = grade_client
        path_id = _seed_path(app, user)
        with app.test_client() as c:
            c.post('/login', data={'username': 'gradetester',
                                   'password': 'pass'})
            body = c.get(f'/lessons/0?path_id={path_id}').get_data(
                as_text=True)
        assert 'data-checkpoint-answers=' in body