"""
Route definitions for the Study-and-Learn MVP.
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.utils import allowed_file
from app.services.document_parser import extract_text
from app.services.summarizer import generate_summary
from app.services.relevance_checker import check_relevance
from app.services.curriculum_generator import generate_study_path

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
    """Handle file upload and process the workflow."""
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
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        try:
            # Retrieve learning goal from session
            learning_goal = session.get('learning_goal', '')
            if not learning_goal:
                flash('Please set a learning goal first', 'error')
                return redirect(url_for('main.index'))
            
            # Step 1: Extract text from the uploaded file
            extracted_text = extract_text(file_path)
            
            # Step 2: Generate summary
            summary = generate_summary(extracted_text)
            
            # Step 3: Check relevance
            relevance_result = check_relevance(learning_goal, extracted_text, summary)
            
            # Step 4: Generate study path
            study_path = generate_study_path(learning_goal, extracted_text, summary)
            
            # Store results in session for display on results page
            # Note: Don't store extracted_text - it can exceed session cookie size limits
            session['summary'] = summary
            session['relevance_result'] = relevance_result
            session['study_path'] = study_path
            session['processed_filename'] = filename
            
            flash(f'File {filename} processed successfully!', 'success')
            return redirect(url_for('main.results'))
            
        except ValueError as e:
            # Handle specific validation errors from our services
            flash(f'Processing error: {str(e)}', 'error')
            return redirect(url_for('main.index'))
        except Exception as e:
            # Handle any other unexpected errors
            flash(f'An unexpected error occurred: {str(e)}', 'error')
            return redirect(url_for('main.index'))
    else:
        flash('Allowed file types are: txt, md, pdf, docx', 'error')
        return redirect(url_for('main.index'))


@bp.route('/results')
def results():
    """Display the results page with summary, relevance, and study path."""
    # Check if we have processed data in session
    if 'summary' not in session:
        flash('No results to display. Please upload a file first.', 'info')
        return redirect(url_for('main.index'))
    
    # Retrieve data from session
    summary = session.get('summary', '')
    relevance_result = session.get('relevance_result', {})
    study_path = session.get('study_path', {})
    filename = session.get('processed_filename', 'unknown file')
    
    return render_template('results.html', 
                         summary=summary,
                         relevance_result=relevance_result,
                         study_path=study_path,
                         filename=filename)


@bp.route('/reset')
def reset():
    """Reset the session and start over."""
    # Clear relevant session data
    session.pop('learning_goal', None)
    session.pop('summary', None)
    session.pop('relevance_result', None)
    session.pop('study_path', None)
    session.pop('processed_filename', None)
    
    flash('Session reset. You can start over.', 'info')
    return redirect(url_for('main.index'))