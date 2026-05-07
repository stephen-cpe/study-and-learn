"""
Flask application factory for the Study-and-Learn MVP.
"""
from flask import Flask


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Import and register routes
    from app import routes
    app.register_blueprint(routes.bp)

    return app