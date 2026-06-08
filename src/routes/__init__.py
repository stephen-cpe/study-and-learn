"""
Routes package — split domain modules attached to a single Blueprint.

The ``bp`` blueprint (registered as ``'main'``) is defined here and
imported by each sub-module to register their routes.  ``url_for``
references remain ``url_for('main.XXX')`` throughout the application.
"""
import logging

from flask import Blueprint

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

MAX_FILES = 5
PASS_THRESHOLD = 80

# ── Import sub-modules so routes are registered ─────────────────────────
from src.routes import auth        # noqa: E402, F401
from src.routes import admin       # noqa: E402, F401
from src.routes import processing  # noqa: E402, F401
from src.routes import lessons     # noqa: E402, F401
from src.routes import dashboard   # noqa: E402, F401

# ── Error Handlers (app-level) ──────────────────────────────────────────
from src import db

@bp.app_errorhandler(400)
def bad_request(e):
    from flask import render_template
    return render_template('error.html', code=400,
                           message='Bad Request',
                           detail='The server could not understand the request.'), 400


@bp.app_errorhandler(403)
def forbidden(e):
    from flask import render_template
    return render_template('error.html', code=403,
                           message='Access Denied',
                           detail='You do not have permission to access this page.'), 403


@bp.app_errorhandler(404)
def not_found(e):
    from flask import render_template
    return render_template('error.html', code=404,
                           message='Page Not Found',
                           detail='The page you are looking for does not exist.'), 404


@bp.app_errorhandler(500)
def internal_error(e):
    db.session.rollback()
    from flask import render_template
    return render_template('error.html', code=500,
                           message='Internal Server Error',
                           detail='Something went wrong on our end. Please try again later.'), 500
