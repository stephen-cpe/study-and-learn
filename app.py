"""
Entry point to run the Flask application.
"""
import os

from dotenv import load_dotenv

load_dotenv()

from src import create_app

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(debug=debug, host=host, port=port)