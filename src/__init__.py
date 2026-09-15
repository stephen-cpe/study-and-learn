"""
Flask application factory for the Study-and-Learn MVP.
"""
import logging
import os

from cachelib import FileSystemCache
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

# ── Extensions (imported here for blueprint access patterns) ─────────────────
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()  # noqa: F401
migrate = Migrate()  # noqa: F401
login_manager = LoginManager()

logger = logging.getLogger(__name__)


def _bool_env(name: str) -> bool:
    """Return True if env var *name* is set to a truthy string."""
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # ── Centralized config ──────────────────────────────────────────────
    from config import Config
    app.config.from_object(Config)
    logger.info(Config.summary())

    # ── SECRET_KEY validation ────────────────────────────────────────────
    # The config default is a known dev-only key. In production (real AI
    # backend, no debug, no CI/mock), a weak SECRET_KEY makes session
    # cookies forgeable. Fail fast in that case. Test/CI/mock environments
    # are exempted because they either set SECRET_KEY via config.update()
    # after create_app() returns, or don't need session security.
    _is_debug = _bool_env('FLASK_DEBUG')
    _is_mock = _bool_env('AI_MOCK')
    _is_ci = _bool_env('CI')
    if app.config['SECRET_KEY'] == 'dev-key-for-testing-only' and not _is_debug and not _is_mock and not _is_ci:
        raise RuntimeError(
            "SECRET_KEY is set to the insecure default 'dev-key-for-testing-only'. "
            "Set the SECRET_KEY environment variable to a strong random string "
            "(e.g. via `python -c \"import secrets; print(secrets.token_hex(32))\"`)."
        )

    # ── PostgreSQL-only database (strict validation) ────────────────────
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql+psycopg2://user:password@localhost:5432/study_and_learn"
        )
    if 'postgresql' not in app.config['SQLALCHEMY_DATABASE_URI']:
        raise RuntimeError(
            f"DATABASE_URL must use PostgreSQL ('postgresql' prefix). "
            f"Got: {app.config['SQLALCHEMY_DATABASE_URI']}"
        )

    # ── CSRF protection (Flask-WTF) ───────────────────────────────────────
    # CSRF is enforced in production; disabled under CI / AI_MOCK / TESTING
    # so the test suite (which uses raw POSTs) keeps passing without tokens.
    # Tests that want to exercise CSRF enforcement set WTF_CSRF_ENABLED=True
    # explicitly (see tests/test_security_task1.py).
    if 'WTF_CSRF_ENABLED' not in app.config:
        app.config['WTF_CSRF_ENABLED'] = not (
            _is_debug or _is_mock or _is_ci
        )
    from flask_wtf import CSRFProtect
    csrf = CSRFProtect(app)
    # Expose the csrf object on the app so tests/routes can inspect it.
    app.extensions['csrf'] = csrf

    # ── Server-side sessions (cachelib-backed) ────────────────────────────
    session_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'data', 'flask_session'
    )
    os.makedirs(session_dir, exist_ok=True)

    app.config['SESSION_CACHELIB'] = FileSystemCache(
        cache_dir=session_dir, threshold=500, mode=0o700
    )

    from flask_session import Session
    Session(app)

    # ── Initialize extensions ─────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    login_manager.login_message_category = 'error'

    # Wire the User model into Flask-Login
    @login_manager.user_loader
    def _load_user(user_id):
        from src.models import User
        return User.query.get(user_id)

    from src import routes
    app.register_blueprint(routes.bp)

    # ── Sweep orphaned background tasks ─────────────────────────────────
    # Rows left 'running' by a previous process (Ctrl+C, restart, redeploy)
    # can never resolve — their request handlers died with it. Flip them
    # to failed so the bell stops showing "running…" forever. Best-effort:
    # missing tables (fresh DB before migrations) must never break startup.
    try:
        with app.app_context():
            from src.services.background_tasks import sweep_orphaned_tasks
            sweep_orphaned_tasks()
    except Exception:
        logger.debug("Background-task sweep skipped at startup", exc_info=True)

    # ── Cache control for HTML and static files ─────────────────────────
    # Flask's default static-file handler sends strong cache headers
    # (12-hour max-age), which causes the browser to keep stale
    # .js and .css files across code changes. This produced a
    # "phantom" bug during manual testing where the new server
    # code was correct but the browser kept running the old
    # client-side JS that fired a 10-minute hard-timeout redirect.
    # Setting ``SEND_FILE_MAX_AGE_DEFAULT=0`` makes the dev server
    # always serve "no-cache" so the browser revalidates every
    # static file on each page load. (In production this would be
    # handled by a CDN or by serving hashed asset names.)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Also prevent the browser from caching rendered HTML pages in the
    # dev server. Without this, a stale dashboard page (rendered before
    # CSRF token inputs were added to its forms) can be served from the
    # browser's back/forward cache, causing POSTs to fail with
    # "CSRF token is missing" because the old form had no token field.
    # In production, HTML caching is handled by Nginx/CDN headers.
    @app.after_request
    def _no_cache_html(response):
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    return app
