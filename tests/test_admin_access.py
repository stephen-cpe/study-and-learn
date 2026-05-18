"""
Tests for Sprint 5 Phase 2.4 — Admin Role, Per-User Lesson Generation Toggle,
and Demo Account Seeding.

Uses the SQLite in-memory fixture pattern established in test_dashboard.py.
"""
import io
import tempfile
import pytest
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User, StudyPath


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
            user = User(username='norm', email='norm@example.com')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'norm', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


def _set_study_path_in_session(client):
    with client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn Python'
        sess['study_path'] = {
            'modules': [{'title': 'Python Basics', 'estimated_effort': '1h'}]
        }
        sess['extracted_texts'] = ['sample text']


def _login_as(client, username, password='pass'):
    client.get('/logout')
    client.post('/login', data={'username': username, 'password': password})


def test_new_user_signup_denied_generation(client):
    rv = client.post('/signup', data={
        'username': 'newbie', 'email': 'newbie@example.com', 'password': 'secret'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'Account created' in rv.data

    _set_study_path_in_session(client)
    rv = client.post('/generate-lessons', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Lesson generation is disabled' in rv.data
    assert b'admin' in rv.data.lower()


def test_can_generate_lessons_user_can_access(monkeypatch, client):
    monkeypatch.setenv('AI_MOCK', 'true')

    user = User.query.filter_by(username='norm').first()
    user.can_generate_lessons = True
    db.session.commit()

    _set_study_path_in_session(client)
    rv = client.post('/generate-lessons', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Generated' in rv.data


def test_admin_bypass_generation(monkeypatch, client):
    monkeypatch.setenv('AI_MOCK', 'true')

    user = User.query.filter_by(username='norm').first()
    user.is_admin = True
    db.session.commit()

    assert user.can_generate_lessons is False

    _set_study_path_in_session(client)
    rv = client.post('/generate-lessons', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Generated' in rv.data


def test_admin_toggle_enables_access(client):
    admin = User(username='super', email='super@example.com', is_admin=True)
    admin.set_password('pass')
    db.session.add(admin)
    db.session.commit()

    target = User.query.filter_by(username='norm').first()
    assert target.can_generate_lessons is False

    _login_as(client, 'super')
    rv = client.get(f'/admin/toggle/{target.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'enabled' in rv.data.lower()

    target_refreshed = db.session.get(User, target.id)
    assert target_refreshed.can_generate_lessons is True


def test_admin_toggle_disables_access(client):
    admin = User(username='super2', email='super2@example.com', is_admin=True)
    admin.set_password('pass')
    db.session.add(admin)
    db.session.commit()

    target = User.query.filter_by(username='norm').first()
    target.can_generate_lessons = True
    db.session.commit()

    _login_as(client, 'super2')
    rv = client.get(f'/admin/toggle/{target.id}', follow_redirects=True)
    assert rv.status_code == 200
    assert b'disabled' in rv.data.lower()

    target_refreshed = db.session.get(User, target.id)
    assert target_refreshed.can_generate_lessons is False


def test_non_admin_cannot_toggle(client):
    rv = client.get('/admin/toggle/some-id', follow_redirects=True)
    assert rv.status_code == 403


def test_seed_demo_creates_bob_and_alice(client):
    admin = User(username='admin_seed', email='admin_seed@example.com', is_admin=True)
    admin.set_password('pass')
    db.session.add(admin)
    db.session.commit()

    _login_as(client, 'admin_seed')
    rv = client.get('/seed-demo', follow_redirects=True)
    assert rv.status_code == 200
    assert b'seeded' in rv.data.lower()

    bob = User.query.filter_by(username='bob').first()
    alice = User.query.filter_by(username='alice').first()
    assert bob is not None
    assert alice is not None
    assert bob.can_generate_lessons is True
    assert alice.can_generate_lessons is True
    assert bob.check_password('demo123')
    assert alice.check_password('demo123')


def test_seed_demo_idempotent(client):
    admin = User(username='admin_idem', email='admin_idem@example.com', is_admin=True)
    admin.set_password('pass')
    db.session.add(admin)
    bob = User(username='bob', email='bob@example.com',
               can_generate_lessons=True)
    bob.set_password('demo123')
    alice = User(username='alice', email='alice@example.com',
                 can_generate_lessons=True)
    alice.set_password('demo123')
    db.session.add_all([bob, alice])
    db.session.commit()

    _login_as(client, 'admin_idem')
    rv = client.get('/seed-demo', follow_redirects=True)
    assert rv.status_code == 200
    assert b'already exist' in rv.data.lower()

    count = User.query.filter_by(username='bob').count()
    assert count == 1
