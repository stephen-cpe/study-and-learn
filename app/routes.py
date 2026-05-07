"""
Route definitions for the Study-and-Learn MVP.
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.utils import allowed_file

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx'}


@bp.route('/')
def index():
    """Return the homepage with forms for learning goal and file upload."""
    return render_template('index.html')


@bp.route('/goal', methods=['POST'])
def set_goal():
    """Handle learning goal submission."""
    goal = request.form.get('learning_goal', '').strip()
    
    if not goal:
        flash('Please enter a learning goal', 'error')
        return redirect(url_for('main.index'))
    
    # Store goal in session
    session['learning_goal'] = goal
    flash('Learning goal saved successfully!', 'success')
    return redirect(url_for('main.index'))


@bp.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload."""
    # Check if file was included in the request
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('main.index'))
    
    file = request.files['file']
    
    # If user does not select file, browser also submits an empty part
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('main.index'))
    
    # Check if file type is allowed
    if file and allowed_file(file.filename):
        # Secure the filename and save file
        filename = file.filename
        upload_folder = current_app.config['UPLOAD_FOLDER']
        # Ensure upload directory exists
        os.makedirs(upload_folder, exist_ok=True)
        file.save(os.path.join(upload_folder, filename))
        flash(f'File {filename} uploaded successfully!', 'success')
        return redirect(url_for('main.index'))
    else:
        flash('Allowed file types are: txt, md, pdf, docx', 'error')
        return redirect(url_for('main.index'))