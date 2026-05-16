"""
Flask application factory for the Study-and-Learn MVP.
"""
import os
from flask import Flask
from cachelib import FileSystemCache

# ── Extensions (imported here for blueprint access patterns) ─────────────────
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager


db = SQLAlchemy()  # noqa: F401
migrate = Migrate()  # noqa: F401
login_manager = LoginManager()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing-only')
    app.config['UPLOAD_FOLDER'] = 'uploads'

    # ── PostgreSQL-only database ──────────────────────────────────────────
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. "
            "Example: postgresql+psycopg2://user:password@localhost:5432/study_and_learn"
        )
    if 'postgresql' not in database_url:
        raise RuntimeError(
            f"DATABASE_URL must use PostgreSQL ('postgresql' prefix). Got: {database_url}"
        )
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # ── Server-side sessions (cachelib-backed) ────────────────────────────
    # TODO: migrate session storage to DB-backed in Sprint 5 Phase 2
    session_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'data', 'flask_session'
    )
    os.makedirs(session_dir, exist_ok=True)

    app.config['SESSION_TYPE'] = 'cachelib'
    app.config['SESSION_CACHELIB'] = FileSystemCache(
        cache_dir=session_dir, threshold=500, mode=0o700
    )
    app.config['SESSION_PERMANENT'] = False

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

    return app
