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
from app.services.rag_retriever import build_rag_context

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx'}
MAX_FILES = 5


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
    """Handle multi-file upload and process the workflow with RAG."""
    files = request.files.getlist('files')

    # Robust empty check: filter out empty filenames
    valid_files = [f for f in files if f and f.filename and f.filename.strip()]

    if not valid_files:
        flash('No valid files selected', 'error')
        return redirect(url_for('main.index'))

    if len(valid_files) > MAX_FILES:
        flash(f'Maximum {MAX_FILES} files allowed', 'error')
        return redirect(url_for('main.index'))
    
    learning_goal = session.get('learning_goal', '')
    if not learning_goal:
        flash('Please set a learning goal first', 'error')
        return redirect(url_for('main.index'))
    
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    
    extracted_texts = []
    filenames = []
    
    for file in files:
        if file.filename and allowed_file(file.filename):
            filename = file.filename
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            try:
                text = extract_text(file_path)
                extracted_texts.append(text)
                filenames.append(filename)
            except ValueError as e:
                flash(f'Error extracting {filename}: {str(e)}', 'error')
                return redirect(url_for('main.index'))
        else:
            flash(f'Skipping invalid file type: {file.filename}', 'warning')
    
    if not extracted_texts:
        flash('No valid files to process', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # Use RAG pipeline to get context from all files
        rag_context = build_rag_context(learning_goal, extracted_texts)
        
        # Fall back to concatenated text if RAG fails
        if not rag_context:
            rag_context = "\n\n".join(extracted_texts)
        
        # Generate summary using RAG context
        summary = generate_summary(rag_context)
        
        # Check relevance using RAG context
        relevance_result = check_relevance(learning_goal, rag_context, summary)
        
        # Generate study path using RAG context
        study_path = generate_study_path(learning_goal, rag_context, summary)
        
        session['summary'] = summary
        session['relevance_result'] = relevance_result
        session['study_path'] = study_path
        session['processed_filename'] = ', '.join(filenames)
        
        flash(f'Processed {len(filenames)} file(s) successfully!', 'success')
        return redirect(url_for('main.results'))
        
    except Exception as e:
        flash(f'Processing error: {str(e)}', 'error')
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