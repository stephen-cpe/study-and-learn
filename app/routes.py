"""
Route definitions for the Study-and-Learn MVP.
"""
from flask import Blueprint, render_template

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Return the homepage."""
    return 'Study-and-Learn MVP'