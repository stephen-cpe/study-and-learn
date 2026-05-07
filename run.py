"""
Entry point to run the Flask application.
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Run the application in debug mode for development
    app.run(debug=True, host='0.0.0.0', port=5000)