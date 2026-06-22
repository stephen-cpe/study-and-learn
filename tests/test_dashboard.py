"""
Tests for Sprint 5 Phase 2.3 — Learner Dashboard + Cancel/Abandon + 3-Lesson Cap UI.

Uses the SQLite in-memory fixture pattern established in test_integration.py.
"""
import io
import tempfile
import pytest
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User, StudyPath, LessonProgress


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
            user = User(username='dashuser', email='dash@example.com')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'dashuser', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


def _make_active_path(client, title='Intro to ML', goal='Learn ML basics'):
    user = User.query.filter_by(username='dashuser').first()
    path = StudyPath(
        user_id=user.id, title=title,
        learning_goal=goal, status='active',
    )
    db.session.add(path)
    db.session.commit()

    for i in range(2):
        lp = LessonProgress(
            study_path_id=path.id, module_index=i,
            score=85, passed=True, completed=True,
        )
        db.session.add(lp)
    db.session.commit()
    return path


def _make_path_no_progress(client, title='Empty Path', goal='Empty'):
    user = User.query.filter_by(username='dashuser').first()
    path = StudyPath(
        user_id=user.id, title=title,
        learning_goal=goal, status='active',
    )
    db.session.add(path)
    db.session.commit()
    return path


def test_dashboard_renders_active_paths(client):
    _make_active_path(client)

    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'My Learning Dashboard' in rv.data
    assert b'Intro to ML' in rv.data
    assert b'100%' in rv.data
    assert b'View Lessons' in rv.data
    assert b'Cancel / Abandon' in rv.data


def test_pre_generation_active_path_shows_continue_setup(client):
    """A pre-generation active path (no LessonProgress rows, content_data is
    None) must show 'Continue Setup' linking to /results — NOT 'View Lessons',
    which would bounce back to /dashboard in a dead-end loop. See the revised
    Option A analysis: this is the single change that kills the loop."""
    _make_path_no_progress(client, title='Pre-Gen Course', goal='Pre-gen')

    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'Continue Setup' in rv.data
    # The Continue Setup link must point at /results, not /lessons
    assert b'/results' in rv.data
    # View Lessons must NOT appear for this card (the link would dead-end)
    assert b'View Lessons' not in rv.data


def test_post_generation_active_path_shows_view_lessons(client):
    """A post-generation active path (LessonProgress rows present) must keep
    showing 'View Lessons' — the Continue Setup branch must NOT fire once
    modules exist."""
    _make_active_path(client, title='Post-Gen Course')

    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'View Lessons' in rv.data
    assert b'Continue Setup' not in rv.data


def test_dashboard_completed_tab(client):
    path = _make_active_path(client)
    path.status = 'completed'
    db.session.commit()

    rv = client.get('/dashboard?tab=completed')
    assert rv.status_code == 200
    assert b'Completed' in rv.data
    assert b'Intro to ML' in rv.data
    assert b'Delete' in rv.data


def test_dashboard_cancelled_tab(client):
    path = _make_active_path(client)
    path.status = 'cancelled'
    db.session.commit()

    rv = client.get('/dashboard?tab=cancelled')
    assert rv.status_code == 200
    assert b'Cancelled' in rv.data
    assert b'Intro to ML' in rv.data
    assert b'Delete' in rv.data


def test_mark_complete_sets_status(client):
    path = _make_active_path(client)

    rv = client.post(f'/study-path/{path.id}/complete', follow_redirects=True)
    assert rv.status_code == 200
    assert b'marked as complete' in rv.data.lower()

    refreshed = db.session.get(StudyPath, path.id)
    assert refreshed.status == 'completed'


def test_mark_complete_blocked_if_not_all_passed(client):
    user = User.query.filter_by(username='dashuser').first()
    path = StudyPath(
        user_id=user.id, title='Partial',
        learning_goal='Goal', status='active',
    )
    db.session.add(path)
    db.session.commit()
    db.session.add_all([
        LessonProgress(study_path_id=path.id, module_index=0, score=90, passed=True, completed=True),
        LessonProgress(study_path_id=path.id, module_index=1, score=70, passed=False, completed=True),
    ])
    db.session.commit()

    rv = client.post(f'/study-path/{path.id}/complete', follow_redirects=True)
    assert rv.status_code == 200
    assert b'must be passed' in rv.data.lower()

    refreshed = db.session.get(StudyPath, path.id)
    assert refreshed.status == 'active'


def test_delete_path_removes_record(client):
    path = _make_active_path(client)
    path.status = 'completed'
    db.session.commit()

    rv = client.post(f'/study-path/{path.id}/delete', follow_redirects=True)
    assert rv.status_code == 200
    assert b'permanently deleted' in rv.data.lower()

    assert db.session.get(StudyPath, path.id) is None
    assert LessonProgress.query.filter_by(study_path_id=path.id).count() == 0


def test_delete_blocked_for_active_path(client):
    path = _make_active_path(client)

    rv = client.post(f'/study-path/{path.id}/delete', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Only completed or cancelled' in rv.data

    assert db.session.get(StudyPath, path.id) is not None


def test_cancel_path_updates_status(client):
    path = _make_active_path(client)

    rv = client.post(f'/study-path/{path.id}/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'has been cancelled' in rv.data
    assert b'My Learning Dashboard' in rv.data

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'cancelled'


def test_cap_warning_banner_shows_at_limit(client):
    user = User.query.filter_by(username='dashuser').first()
    for i in range(3):
        path = StudyPath(
            user_id=user.id, title=f'Course {i}',
            learning_goal=f'Goal {i}', status='active',
        )
        db.session.add(path)
    db.session.commit()

    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'Lesson Cap Reached' in rv.data
    assert b'maximum of 3 active lessons' in rv.data.lower()


def test_empty_dashboard_shows_start_prompt(client):
    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'No active lessons' in rv.data
    assert b'Start New Lesson' in rv.data
    assert b'Upload materials' in rv.data


def test_cancel_nonexistent_path_flashes_error(client):
    rv = client.post('/study-path/nonexistent-id/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Study path not found' in rv.data


def test_cannot_cancel_other_users_path(client):
    other = User(username='other', email='other@example.com')
    other.set_password('pass')
    db.session.add(other)
    db.session.commit()
    path = StudyPath(
        user_id=other.id, title='Other Path',
        learning_goal='Secret', status='active',
    )
    db.session.add(path)
    db.session.commit()

    rv = client.post(f'/study-path/{path.id}/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Study path not found' in rv.data

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'active'


def test_reset_preserves_paths_with_lessons(client):
    path = _make_active_path(client)

    rv = client.get('/reset', follow_redirects=True)
    assert rv.status_code == 200

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'active', (
        "Paths with generated lessons should remain active after reset"
    )


def test_reset_cancels_paths_without_lessons(client):
    path = _make_path_no_progress(client)

    rv = client.get('/reset', follow_redirects=True)
    assert rv.status_code == 200

    path_refreshed = db.session.get(StudyPath, path.id)
    assert path_refreshed.status == 'cancelled', (
        "Paths with zero LessonProgress rows should be cancelled on reset"
    )


# ── UX navigation-flow fix tests ──────────────────────────────────────
# Regression coverage for the "lessons navigation incoherence" defect:
#   A. get_lessons now returns lessons for completed/cancelled paths
#      (covered in test_lesson_repository.py at the repo layer).
#   C. /lessons?path_id=<id> renders the module list for any status,
#      with the correct path-level action buttons (Mark Complete /
#      Cancel / Back to Completed tab) instead of the legacy
#      "Back to Results" / "Start Over" pair.
#   D. Bare /lessons (no path_id) redirects to /dashboard; the
#      redundant "My Lessons" nav button is gone from base.html.


def _make_path_with_lessons(client, status='active', title='Course',
                            goal='Learn', all_passed=True):
    user = User.query.filter_by(username='dashuser').first()
    path = StudyPath(
        user_id=user.id, title=title,
        learning_goal=goal, status=status,
    )
    db.session.add(path)
    db.session.commit()

    import json as _json
    lessons = [
        {'index': 0, 'module_title': 'Module One', 'estimated_effort': '1h',
         'lesson': {'slides': [{'type': 'title', 'title': 'M1'}]},
         'quiz': {'questions': []}, 'checkpoints': {},
         'completed': all_passed, 'score': 90 if all_passed else None,
         'passed': all_passed},
        {'index': 1, 'module_title': 'Module Two', 'estimated_effort': '1h',
         'lesson': {'slides': [{'type': 'title', 'title': 'M2'}]},
         'quiz': {'questions': []}, 'checkpoints': {},
         'completed': all_passed, 'score': 95 if all_passed else None,
         'passed': all_passed},
    ]
    path.content_data = _json.dumps(lessons)
    for i, l in enumerate(lessons):
        db.session.add(LessonProgress(
            study_path_id=path.id, module_index=i,
            score=l['score'], passed=l['passed'], completed=l['completed'],
        ))
    db.session.commit()
    return path


def test_bare_lessons_redirects_to_dashboard(client):
    """Fix D: GET /lessons with no path_id must redirect to /dashboard
    (the canonical list-of-paths page) instead of silently grabbing the
    most recent active path.
    """
    rv = client.get('/lessons', follow_redirects=False)
    assert rv.status_code in (301, 302, 303, 307, 308)
    assert '/dashboard' in rv.headers.get('Location', '')


def test_lessons_page_works_for_completed_path(client):
    """Fix A+C: /lessons?path_id=<completed-id> renders the module list
    (no flash error, no redirect to /results). Previously dead-ended.
    """
    path = _make_path_with_lessons(client, status='completed',
                                   title='Finished Course')
    rv = client.get(f'/lessons?path_id={path.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Module One' in rv.data
    assert b'Module Two' in rv.data


def test_lessons_page_shows_mark_complete_when_all_passed(client):
    """Fix C: active path with all modules passed shows a Mark Complete
    button on the lessons page (previously only on the dashboard)."""
    path = _make_path_with_lessons(client, status='active',
                                   title='Active Course', all_passed=True)
    rv = client.get(f'/lessons?path_id={path.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Mark Complete' in rv.data
    # Legacy dead-end buttons must be gone
    assert b'Back to Results' not in rv.data
    assert b'>Start Over<' not in rv.data


def test_lessons_page_shows_cancel_when_not_all_passed(client):
    """Fix C: active path with incomplete modules shows Cancel / Abandon
    (and Start New Lesson), not Mark Complete."""
    path = _make_path_with_lessons(client, status='active',
                                   title='Partial Course', all_passed=False)
    rv = client.get(f'/lessons?path_id={path.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Cancel / Abandon' in rv.data
    assert b'Start New Lesson' in rv.data
    assert b'Mark Complete' not in rv.data


def test_lessons_page_shows_back_to_completed_tab_for_completed_path(client):
    """Fix C: completed path lessons page shows a Back to Completed Tab
    button instead of Mark Complete / Cancel."""
    path = _make_path_with_lessons(client, status='completed',
                                   title='Done Course', all_passed=True)
    rv = client.get(f'/lessons?path_id={path.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Back to Completed Tab' in rv.data
    assert b'Mark Complete' not in rv.data
    assert b'Cancel / Abandon' not in rv.data


def test_lessons_page_shows_back_to_dashboard(client):
    """Fix C: every lessons page has a Back to Dashboard button."""
    path = _make_path_with_lessons(client, status='active',
                                   title='Any Course')
    rv = client.get(f'/lessons?path_id={path.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Back to Dashboard' in rv.data


def test_my_lessons_nav_button_removed(client):
    """Fix D: the redundant 'My Lessons' nav button is gone from base.html."""
    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'>My Lessons<' not in rv.data


# ── Retro confirm modal tests ─────────────────────────────────────────
# The native window.confirm() dialogs on Cancel/Delete forms have been
# replaced with a shared themed Bootstrap modal (#confirm-modal) wired
# via data-confirm="true" attributes. These tests assert the modal
# markup is present on authenticated pages, that the destructive forms
# carry the data-confirm attributes (not onsubmit=confirm()), and that
# the legacy native confirm() call is gone.


def test_confirm_modal_markup_present_on_dashboard(client):
    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'id="confirm-modal"' in rv.data
    assert b'retro-confirm-modal' in rv.data
    assert b'confirm-modal-confirm' in rv.data


def test_cancel_form_uses_data_confirm_not_onsubmit(client):
    path = _make_active_path(client)
    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b'data-confirm="true"' in rv.data
    assert b'data-confirm-title="Cancel' in rv.data
    # Legacy native confirm() call must be gone
    assert b"onsubmit=\"return confirm(" not in rv.data
    assert b"return confirm(" not in rv.data


def test_delete_form_uses_data_confirm_not_onsubmit(client):
    path = _make_active_path(client)
    path.status = 'completed'
    db.session.commit()
    rv = client.get('/dashboard?tab=completed')
    assert rv.status_code == 200
    assert b'data-confirm-title="Permanently delete' in rv.data
    assert b'data-confirm-action="Delete Forever"' in rv.data
    assert b"return confirm(" not in rv.data


def test_cancel_still_works_without_native_confirm(client):
    """The form must still POST successfully — the modal is a client-side
    gate, not a server-side one, so a direct POST (as in tests / curl)
    must still cancel the path."""
    path = _make_active_path(client)
    rv = client.post(f'/study-path/{path.id}/cancel', follow_redirects=True)
    assert rv.status_code == 200
    assert b'has been cancelled' in rv.data
    assert db.session.get(StudyPath, path.id).status == 'cancelled'


def test_delete_still_works_without_native_confirm(client):
    path = _make_active_path(client)
    path.status = 'completed'
    db.session.commit()
    rv = client.post(f'/study-path/{path.id}/delete', follow_redirects=True)
    assert rv.status_code == 200
    assert b'permanently deleted' in rv.data
    assert db.session.get(StudyPath, path.id) is None
