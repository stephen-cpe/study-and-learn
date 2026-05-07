"""
Flask application factory for the Study-and-Learn MVP.
"""
import os
from flask import Flask


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Set secret key for session and flash messages
    # Use environment variable in production, fallback for development only
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing-only')
    # Configure upload folder
    app.config['UPLOAD_FOLDER'] = 'uploads'

    # Import and register routes
    from app import routes
    app.register_blueprint(routes.bp)

    return app