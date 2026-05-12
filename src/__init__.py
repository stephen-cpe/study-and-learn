"""
Flask application factory for the Study-and-Learn MVP.
"""
import os
from flask import Flask
from cachelib import FileSystemCache


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing-only')
    app.config['UPLOAD_FOLDER'] = 'uploads'

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

    from src import routes
    app.register_blueprint(routes.bp)

    return app