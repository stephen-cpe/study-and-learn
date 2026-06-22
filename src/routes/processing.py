"""
Processing routes — document upload, text extraction, AI pipeline, and results.
"""
import logging
import os

from flask import (current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user

from src.repositories.lesson_repo import (
    create_study_path,
    get_learning_goal as _db_get_goal,
)
from src.routes import MAX_FILES, bp
from src.routes._helpers import _resolve_hashes, _resolve_texts
from src.services import progress_tracker
from src.services.curriculum_generator import generate_study_path
from src.services.document_parser import extract_text_with_vision
from src.services.exceptions import StudyAndLearnError
from src.services.rag_retriever import (
    build_rag_context,
    build_rag_context_from_hashes,
)
from src.services.relevance_checker import check_relevance
from src.services.summarizer import generate_summary
from src.services.vision_parser import hash_file, is_content_registered
from src.utils import allowed_file

logger = logging.getLogger(__name__)


@bp.route('/health')
def health():
    return jsonify({'status': 'healthy'})


@bp.route('/')
def index():
    from src.models import StudyPath
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('main.admin'))
    goals = []
    if current_user.is_authenticated:
        paths = StudyPath.query.filter_by(
            user_id=current_user.id, status='active'
        ).order_by(StudyPath.created_at.asc()).all()
        goals = [{'id': p.id, 'title': p.learning_goal or p.title} for p in paths]
    return render_template('index.html', goals=goals,
                           session_goal=session.get('learning_goal', ''))


@bp.route('/results')
def results():
    summary = session.get('summary', '')
    relevance_result = session.get('relevance_result', {})
    study_path = session.get('study_path', {})
    filename = session.get('processed_filename', 'unknown file')
    filenames = session.get('uploaded_filenames', [])
    learning_goal = session.get('learning_goal', '')

    if not summary and current_user.is_authenticated:
        goal = _db_get_goal(current_user)
        if goal:
            learning_goal = goal

    if not summary:
        flash('No results to display. Please upload a file first.', 'info')
        return redirect(url_for('main.index'))

    return render_template('results.html',
                           summary=summary,
                           relevance_result=relevance_result,
                           study_path=study_path,
                           filename=filename,
                           filenames=filenames,
                           learning_goal=learning_goal)


@bp.route('/progress')
def progress():
    task_id = request.args.get('task_id', '') or session.sid
    status = progress_tracker.get_progress(task_id)
    if status is None:
        return jsonify({'stage': -1, 'label': 'No task', 'pct': 0, 'mascot': ''})
    return jsonify(status)


@bp.route('/process', methods=['POST'])
def process():
    task_id = request.form.get('task_id', '') or None
    is_ajax = task_id is not None

    goal = request.form.get('learning_goal', '').strip()
    files = request.files.getlist('files')
    valid_files = [f for f in files if f and f.filename and f.filename.strip()]

    def _error(msg):
        if is_ajax:
            if task_id:
                progress_tracker.cleanup_task(task_id)
            return jsonify({'error': msg}), 400
        flash(msg, 'error')
        return redirect(url_for('main.index'))

    if not goal:
        return _error('Please enter a learning goal')
    if not valid_files:
        return _error('No valid files selected')
    if len(valid_files) > MAX_FILES:
        return _error(f'Maximum {MAX_FILES} files allowed')

    if is_ajax:
        progress_tracker.create_task(task_id=task_id, stages=progress_tracker.PROCESS_STAGES)

    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)

    extracted_texts = []
    filenames = []
    file_hashes = []

    if is_ajax:
        progress_tracker.update_progress(task_id, 1)

    for file in valid_files:
        if not allowed_file(file.filename):
            if is_ajax:
                progress_tracker.cleanup_task(task_id)
                return jsonify({'error': f'Invalid file type: {file.filename}'}), 400
            flash(f'Skipping invalid file type: {file.filename}', 'warning')
            continue

        filename = file.filename
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)

        file_hash = hash_file(file_path)
        file_hashes.append(file_hash)

        ext = os.path.splitext(filename)[1].lower()
        if ext in ('.txt', '.md'):
            try:
                text = extract_text_with_vision(file_path)
                extracted_texts.append(text)
                filenames.append(filename)
            except ValueError as e:
                if is_ajax and task_id:
                    progress_tracker.mark_error(task_id, mascot_msg='Couldn\'t read a file')
                if is_ajax:
                    progress_tracker.cleanup_task(task_id)
                    return jsonify({'error': f'Error extracting {filename}: {str(e)}'}), 400
                flash(f'Error extracting {filename}: {str(e)}', 'error')
                return redirect(url_for('main.index'))
            continue

        # Check content registry for deduplication
        from src.models import ContentRegistry
        try:
            existing_collection = is_content_registered(file_hash)
            if existing_collection:
                entry = ContentRegistry.query.filter_by(file_hash=file_hash).first()
                if entry and entry.extracted_text:
                    extracted_texts.append(entry.extracted_text)
                    filenames.append(filename)
                    continue
        except Exception as e:
            logger.warning("ContentRegistry lookup failed for hash %s: %s", file_hash[:8], str(e))

        def ocr_progress(stage_name, current, total):
            if is_ajax and task_id:
                if stage_name == "ocr":
                    progress_tracker.update_progress(task_id, 2)
                elif stage_name == "figure":
                    progress_tracker.update_progress(task_id, 3)

        try:
            text = extract_text_with_vision(file_path, progress_callback=ocr_progress)
            extracted_texts.append(text)
            filenames.append(filename)
        except ValueError as e:
            if is_ajax and task_id:
                progress_tracker.mark_error(task_id, mascot_msg='Couldn\'t read a file')
            if is_ajax:
                progress_tracker.cleanup_task(task_id)
                return jsonify({'error': f'Error extracting {filename}: {str(e)}'}), 400
            flash(f'Error extracting {filename}: {str(e)}', 'error')
            return redirect(url_for('main.index'))

    if not extracted_texts:
        if is_ajax:
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': 'No valid files to process'}), 400
        flash('No valid files to process', 'error')
        return redirect(url_for('main.index'))

    try:
        if is_ajax:
            progress_tracker.update_progress(task_id, 4)

        if file_hashes:
            rag_context = build_rag_context_from_hashes(goal, file_hashes)
        else:
            rag_context = build_rag_context(goal, extracted_texts)
        if not rag_context:
            rag_context = "\n\n".join(extracted_texts)

        if is_ajax:
            progress_tracker.update_progress(task_id, 5)

        summary = generate_summary(rag_context)
        if is_ajax:
            progress_tracker.update_progress(task_id, 6)

        relevance_result = check_relevance(goal, rag_context, summary)
        if is_ajax:
            progress_tracker.update_progress(task_id, 7)

        if relevance_result.get('relevance_label') != 'weak':
            study_path = generate_study_path(goal, rag_context, summary)
        else:
            study_path = {}

        session['learning_goal'] = goal
        session['summary'] = summary
        session['relevance_result'] = relevance_result
        session['study_path'] = study_path
        session['processed_filename'] = ', '.join(filenames)
        session['uploaded_filenames'] = filenames
        session['extracted_texts'] = extracted_texts
        session['file_hashes'] = file_hashes

        if current_user.is_authenticated:
            if not current_user.can_start_new_lesson():
                flash('You already have 3 active lessons. Complete or cancel one before starting a new one.', 'error')
                if is_ajax:
                    progress_tracker.cleanup_task(task_id)
                    return jsonify({'redirect': url_for('main.dashboard')})
                return redirect(url_for('main.dashboard'))
            path_title = study_path.get('title', goal[:50])
            create_study_path(current_user, path_title, goal,
                              extracted_texts=extracted_texts,
                              file_hashes=file_hashes,
                              file_names=filenames)

        if is_ajax:
            progress_tracker.update_progress(task_id, 8)
            progress_tracker.cleanup_task(task_id)
            return jsonify({'redirect': url_for('main.results')})

        flash(f'Processed {len(filenames)} file(s) successfully!', 'success')
        return redirect(url_for('main.results'))

    except StudyAndLearnError as e:
        logger.error("Processing failed: %s", str(e))
        if is_ajax and task_id:
            progress_tracker.mark_error(task_id, mascot_msg='Processing failed — please retry')
        if is_ajax:
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': str(e)}), 500
        flash(str(e), 'error')
        return redirect(url_for('main.index'))
    except Exception as e:
        logger.error("Unexpected processing error", exc_info=True)
        if is_ajax and task_id:
            progress_tracker.mark_error(task_id, mascot_msg='Unexpected error — please retry')
        if is_ajax:
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('main.index'))
