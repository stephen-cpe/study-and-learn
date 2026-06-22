"""
Tests for Sprint 5 Phase 1.4 — Sign-up, login, logout routes.

The fixture below overrides SQLALCHEMY_DATABASE_URI to an in-memory SQLite DB
so auth tests run quickly and in isolation. The real DATABASE_URL is still
set first so the app factory's PostgreSQL validation passes at startup.
"""
import pytest
import tempfile
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User


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
        # Override to SQLite for isolated auth unit tests only
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        # Remove sqlalchemy extension so init_app can re-register with the new URI
        app_instance.extensions.pop('sqlalchemy', None)
        # Re-init to build an SQLite engine for this app
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            with app_instance.test_client() as c:
                yield c
            db.session.remove()
            db.drop_all()


def test_signup_creates_user_and_logs_in(client):
    """POST /signup creates a user, hashes password, and logs them in."""
    rv = client.post('/signup', data={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'secret123'
    }, follow_redirects=True)
    assert rv.status_code == 200

    user = User.query.filter_by(username='newuser').first()
    assert user is not None
    assert user.email == 'new@example.com'
    assert user.password_hash != 'secret123'
    assert user.check_password('secret123')


def test_login_valid_credentials(client):
    """POST /login with valid credentials logs the user in."""
    user = User(username='alice', email='alice@example.com')
    user.set_password('correct')
    db.session.add(user)
    db.session.commit()

    rv = client.post('/login', data={
        'username': 'alice',
        'password': 'correct'
    }, follow_redirects=True)
    assert rv.status_code == 200


def test_login_invalid_password(client):
    """POST /login with wrong password shows error and does not log in."""
    user = User(username='bob', email='bob@example.com')
    user.set_password('rightpass')
    db.session.add(user)
    db.session.commit()

    rv = client.post('/login', data={
        'username': 'bob',
        'password': 'wrongpass'
    }, follow_redirects=True)
    assert rv.status_code == 200
    # Should still show login form (redirected back to login page with flash)
    assert b'Invalid username or password' in rv.data or b'Log In' in rv.data


def test_login_nonexistent_user(client):
    """POST /login with unknown username shows error and does not log in."""
    rv = client.post('/login', data={
        'username': 'nobody',
        'password': 'anypass'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'Invalid username or password' in rv.data or b'Log In' in rv.data


def test_login_get_redirects_to_index(client):
    """GET /login redirects to the index page (login form lives there)."""
    rv = client.get('/login', follow_redirects=False)
    assert rv.status_code == 302
    assert '/process' in rv.headers.get('Location', '') or rv.location.endswith('/')


def test_login_get_follows_to_index(client):
    """GET /login with follow_redirects renders the index page."""
    rv = client.get('/login', follow_redirects=True)
    assert rv.status_code == 200


def test_logout_clears_flask_login_session(client):
    """GET /logout clears the Flask-Login session."""
    user = User(username='charlie', email='charlie@example.com')
    user.set_password('pass')
    db.session.add(user)
    db.session.commit()

    # Log in first
    client.post('/login', data={'username': 'charlie', 'password': 'pass'})

    # Then log out
    rv = client.get('/logout', follow_redirects=True)
    assert rv.status_code == 200
    assert b'logged out' in rv.data.lower() or b'Study' in rv.data


def test_duplicate_username_rejected(client):
    """POST /signup with an existing username is rejected."""
    user = User(username='taken', email='first@example.com')
    user.set_password('pass')
    db.session.add(user)
    db.session.commit()

    rv = client.post('/signup', data={
        'username': 'taken',
        'email': 'second@example.com',
        'password': 'pass'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'already taken' in rv.data or b'Sign Up' in rv.data
