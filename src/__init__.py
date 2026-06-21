"""
Flask application factory for the Study-and-Learn MVP.
"""
import os
import logging
from flask import Flask
from cachelib import FileSystemCache

# ── Extensions (imported here for blueprint access patterns) ─────────────────
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager


db = SQLAlchemy()  # noqa: F401
migrate = Migrate()  # noqa: F401
login_manager = LoginManager()

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # ── Centralized config ──────────────────────────────────────────────
    from config import Config
    app.config.from_object(Config)
    logger.info(Config.summary())

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

    # ── Static-file cache control ───────────────────────────────────────
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

    return app
