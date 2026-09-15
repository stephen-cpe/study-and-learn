"""
Processing routes — document upload, text extraction, AI pipeline, and results.
"""
import logging
import os
import uuid

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from src.models import LessonProgress, StudyPath
from src.repositories.lesson_repo import (
    create_study_path,
    get_most_recent_active_path,
)
from src.repositories.lesson_repo import (
    get_learning_goal as _db_get_goal,
)
from src.routes import MAX_FILES, bp
from src.services import progress_tracker
from src.services.curriculum_generator import generate_study_path
from src.services.document_parser import extract_text_with_vision
from src.services.exceptions import StudyAndLearnError
from src.services.rag_retriever import (
    build_full_coverage_context,
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
    from src.models import PATH_STATUS_ACTIVE, StudyPath
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('main.admin'))
    goals = []
    if current_user.is_authenticated:
        paths = StudyPath.query.filter_by(
            user_id=current_user.id, status=PATH_STATUS_ACTIVE
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
                           learning_goal=learning_goal,
                           coverage_ratio=session.get('coverage_ratio'))


@bp.route('/progress')
def progress():
    task_id = request.args.get('task_id', '') or session.sid
    status = progress_tracker.get_progress(task_id)
    if status is None:
        return jsonify({'stage': -1, 'label': 'No task', 'pct': 0, 'mascot': ''})
    return jsonify(status)


@bp.route('/tasks')
@login_required
def list_background_tasks():
    """Return the user's durable background tasks + unread badge count."""
    from src.services import background_tasks as _bt
    tasks = _bt.list_tasks(current_user.id)
    return jsonify({'tasks': tasks, 'unread': _bt.unread_count(current_user.id)})


@bp.route('/tasks/<task_id>/read', methods=['POST'])
@login_required
def mark_background_task_read(task_id):
    """Mark a background task as read (clears it from the bell badge)."""
    from src.services import background_tasks as _bt
    ok = _bt.mark_read(task_id, current_user.id)
    if not ok:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify({'success': True, 'unread': _bt.unread_count(current_user.id)})


@bp.route('/tasks/<task_id>/dismiss', methods=['POST'])
@login_required
def dismiss_background_task(task_id):
    """Delete one finished task so it disappears from the bell menu."""
    from src.services import background_tasks as _bt
    ok = _bt.dismiss_task(task_id, current_user.id)
    if not ok:
        return jsonify({'error': 'Task not found or still running'}), 404
    return jsonify({'success': True, 'unread': _bt.unread_count(current_user.id)})


@bp.route('/tasks/clear', methods=['POST'])
@login_required
def clear_background_tasks():
    """Delete all finished tasks for the bell menu (running ones are kept)."""
    from src.services import background_tasks as _bt
    cleared = _bt.clear_finished(current_user.id)
    return jsonify({'success': True, 'cleared': cleared,
                    'unread': _bt.unread_count(current_user.id)})


@bp.route('/mascot/line')
@login_required
def mascot_line():
    """Return a short, personalized mascot line for the CRT speech bubble.

    Query params:
        context: 'idle' (default), 'dashboard', 'lessons',
                 'lesson_complete', 'error', 'progress'
        path_id: optional — if provided, use that path's context;
                 otherwise fall back to the most recent active path.

    Returns:
        {"text": "...", "state": "idle"} — never errors (always 200).
    """
    from src.services.mascot_lines import generate_line

    event = request.args.get('context', 'idle').lower()
    valid = {'idle', 'dashboard', 'lessons', 'lesson_complete',
             'error', 'progress'}
    if event not in valid:
        event = 'idle'

    # Determine the learner's current study path + progress
    path_title = None
    progress_pct = None
    page = event if event in ('dashboard', 'lessons') else None

    path_id = request.args.get('path_id')
    if path_id:
        path = StudyPath.query.filter_by(
            id=path_id, user_id=current_user.id
        ).first()
    else:
        path = get_most_recent_active_path(current_user)

    if path and path.content_data:
        path_title = path.title
        progress_rows = LessonProgress.query.filter_by(
            study_path_id=path.id
        ).all()
        total = len(progress_rows)
        if total > 0:
            passed = sum(1 for r in progress_rows if r.passed)
            progress_pct = round((passed / total) * 100)

    line = generate_line(
        user_id=current_user.id,
        display_name=current_user.display_name,
        event=event,
        path_title=path_title,
        progress_pct=progress_pct,
        page=page,
    )
    return jsonify({'text': line, 'state': 'talk' if event != 'error' else 'error'})


@bp.route('/process', methods=['POST'])
@login_required
def process():
    task_id = request.form.get('task_id', '') or None
    is_ajax = task_id is not None

    goal = request.form.get('learning_goal', '').strip()
    files = request.files.getlist('files')
    valid_files = [f for f in files if f and f.filename and f.filename.strip()]

    def _error(msg):
        if is_ajax:
            if task_id:
                from src.services import background_tasks as _bt
                _bt.fail_task(task_id, error=msg)
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
        progress_tracker.create_task(
            task_id=task_id,
            stages=progress_tracker.PROCESS_STAGES,
            display_name=current_user.display_name,
        )
        # Durable bell record (Phase 1): other tabs poll /tasks for this.
        from src.services import background_tasks as _bt
        _bt.create_task(task_id, current_user.id, kind='process',
                        label=f"Processing: {goal[:80]}")

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
                from src.services import background_tasks as _bt
                _bt.fail_task(task_id, error=f'Invalid file type: {file.filename}')
                progress_tracker.cleanup_task(task_id)
                return jsonify({'error': f'Invalid file type: {file.filename}'}), 400
            flash(f'Skipping invalid file type: {file.filename}', 'warning')
            continue

        # ── Two-step save for path-traversal safety + on-disk dedup ───────────
        # Step 1: Save to a uuid-prefixed temp path (prevents path traversal
        # via crafted filenames like "../../app.py").
        original_filename = file.filename
        safe_name = secure_filename(original_filename)
        if not safe_name:
            safe_name = "upload"
        temp_filename = f"_tmp_{uuid.uuid4().hex}_{safe_name}"
        temp_path = os.path.join(upload_folder, temp_filename)
        file.save(temp_path)

        file_hash = hash_file(temp_path)
        file_hashes.append(file_hash)

        # Step 2: Check the content registry for deduplication BEFORE committing
        # the file to its permanent location. If the same content was
        # previously uploaded (by any user), delete the temp file — the
        # extracted text is cached in ContentRegistry and the ChromaDB
        # collection already exists. No need to keep the raw upload.
        from src.models import ContentRegistry
        try:
            existing_collection = is_content_registered(file_hash)
            if existing_collection:
                entry = ContentRegistry.query.filter_by(file_hash=file_hash).first()
                if entry and entry.extracted_text:
                    extracted_texts.append(entry.extracted_text)
                    filenames.append(original_filename)
                    os.remove(temp_path)
                    continue
        except Exception as e:
            logger.warning("ContentRegistry lookup failed for hash %s: %s", file_hash[:8], str(e))

        # Step 3: New content — move the temp file to a deterministic
        # hash-based name so the same content always maps to the same
        # on-disk path. A re-upload of the same file overwrites itself
        # instead of accumulating duplicates.
        disk_filename = f"{file_hash[:16]}_{safe_name}"
        file_path = os.path.join(upload_folder, disk_filename)
        os.replace(temp_path, file_path)

        ext = os.path.splitext(original_filename)[1].lower()
        if ext in ('.txt', '.md'):
            try:
                text = extract_text_with_vision(file_path)
                extracted_texts.append(text)
                filenames.append(original_filename)
            except ValueError as e:
                if is_ajax and task_id:
                    progress_tracker.mark_error(task_id, mascot_msg="Couldn't read a file")
                if is_ajax:
                    from src.services import background_tasks as _bt
                    _bt.fail_task(task_id, error=f'Error extracting {original_filename}: {str(e)}')
                    progress_tracker.cleanup_task(task_id)
                    return jsonify({'error': f'Error extracting {original_filename}: {str(e)}'}), 400
                flash(f'Error extracting {original_filename}: {str(e)}', 'error')
                return redirect(url_for('main.index'))
            continue

        def ocr_progress(stage_name, current, total):
            if is_ajax and task_id:
                if stage_name == "ocr":
                    progress_tracker.update_progress(task_id, 2)
                elif stage_name == "figure":
                    progress_tracker.update_progress(task_id, 3)

        try:
            text = extract_text_with_vision(file_path, progress_callback=ocr_progress)
            extracted_texts.append(text)
            filenames.append(original_filename)
        except ValueError as e:
            if is_ajax and task_id:
                progress_tracker.mark_error(task_id, mascot_msg="Couldn't read a file")
            if is_ajax:
                from src.services import background_tasks as _bt
                _bt.fail_task(task_id, error=f'Error extracting {original_filename}: {str(e)}')
                progress_tracker.cleanup_task(task_id)
                return jsonify({'error': f'Error extracting {original_filename}: {str(e)}'}), 400
            flash(f'Error extracting {original_filename}: {str(e)}', 'error')
            return redirect(url_for('main.index'))

    if not extracted_texts:
        if is_ajax:
            from src.services import background_tasks as _bt
            _bt.fail_task(task_id, error='No valid files to process')
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': 'No valid files to process'}), 400
        flash('No valid files to process', 'error')
        return redirect(url_for('main.index'))

    try:
        if is_ajax:
            progress_tracker.update_progress(task_id, 4)

        # Every accepted file appends its hash before the dedup `continue`
        # and the empty-extraction early-return above, so file_hashes is
        # guaranteed non-empty here.
        #
        # Stage 4 (index build) is done; stage 5 is the map step of the
        # full-coverage pipeline (every extracted chunk is summarized in
        # reading order), and the returned context is grounded in the
        # whole document rather than only the most relevant chunks.  The
        # digest + the budget-sized retrieved context are combined into
        # ``rag_context``.
        #
        # The map step is the long pole on cloud backends (one LLM call per
        # section), so the callback publishes a *live, rotating* status
        # message — section number + short label + busy mascot — on every
        # completed section.  Without this the bubble stays frozen on the
        # previous stage and the JS stale-timeout handler overwrites it
        # with a permanent "hang tight!" even though work is progressing.
        _MAP_LABELS = (
            'Reading sections',
            'Summarizing concepts',
            'Extracting key points',
            'Linking ideas',
        )

        def _map_progress(done, total):
            if not (is_ajax and task_id):
                return
            pct = min(80, 55 + int((done / max(total, 1)) * 25))
            label = _MAP_LABELS[(done - 1) % len(_MAP_LABELS)]
            # Keep the bubble line inside the CRT width budget (<= 35 chars
            # incl. the counter) so it never wraps awkwardly on the mascot.
            mascot_msg = f'{label} {done}/{total}...'
            if len(mascot_msg) > 35:
                mascot_msg = f'{label} {done}/{total}'
            progress_tracker.update_cosmetic(
                task_id,
                pct=pct,
                label=label,
                mascot=mascot_msg,
                mascot_state='busy',
            )

        full = build_full_coverage_context(
            goal, file_hashes, filenames,
            top_k=40,
            progress_callback=_map_progress if is_ajax else None,
        )
        rag_context = full.get('context_text', '')
        content_digest = full.get('content_digest', '')
        coverage_ratio = full.get('coverage_ratio')

        if not rag_context:
            rag_context = "\n\n".join(extracted_texts)
            if is_ajax and task_id:
                progress_tracker.update_cosmetic(
                    task_id,
                    mascot='RAG retrieval failed — using full text instead.',
                    mascot_state='error',
                )

        if is_ajax:
            progress_tracker.update_progress(task_id, 6)

        summary = generate_summary(rag_context)
        if is_ajax:
            progress_tracker.update_progress(task_id, 7)

        relevance_result = check_relevance(goal, rag_context, summary)
        if is_ajax:
            progress_tracker.update_progress(task_id, 8)

        if relevance_result.get('relevance_label') != 'weak':
            study_path = generate_study_path(goal, rag_context, summary)
        else:
            study_path = {}

        # Store the document digest + coverage ratio on the StudyPath so the
        # lesson-generation route can reuse the full-coverage context
        # without re-running the expensive map step.
        session['learning_goal'] = goal
        session['summary'] = summary
        session['relevance_result'] = relevance_result
        session['study_path'] = study_path
        session['processed_filename'] = ', '.join(filenames)
        session['uploaded_filenames'] = filenames
        session['extracted_texts'] = extracted_texts
        session['file_hashes'] = file_hashes
        session['content_digest'] = content_digest
        session['coverage_ratio'] = coverage_ratio

        if current_user.is_authenticated:
            if not current_user.can_start_new_lesson():
                flash('You already have 3 active lessons. Complete or cancel one before starting a new one.', 'error')
                if is_ajax:
                    from src.services import background_tasks as _bt
                    _bt.finish_task(task_id, result_url=url_for('main.dashboard'),
                                    label='At cap — see dashboard')
                    progress_tracker.cleanup_task(task_id)
                    return jsonify({'redirect': url_for('main.dashboard')})
                return redirect(url_for('main.dashboard'))
            path_title = study_path.get('title', goal[:50])
            create_study_path(current_user, path_title, goal,
                              extracted_texts=extracted_texts,
                              file_hashes=file_hashes,
                              file_names=filenames,
                              content_digest=content_digest or None,
                              modules=study_path.get('modules'),
                              summary=summary,
                              relevance_result=relevance_result)

        if is_ajax:
            from src.services import background_tasks as _bt
            _bt.finish_task(task_id, result_url=url_for('main.results'),
                            label=f"Results: {goal[:80]}")
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
            from src.services import background_tasks as _bt
            _bt.fail_task(task_id, error=str(e))
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': str(e)}), 500
        flash(str(e), 'error')
        return redirect(url_for('main.index'))
    except Exception:
        logger.error("Unexpected processing error", exc_info=True)
        if is_ajax and task_id:
            progress_tracker.mark_error(task_id, mascot_msg='Unexpected error — please retry')
        if is_ajax:
            from src.services import background_tasks as _bt
            _bt.fail_task(task_id, error='An unexpected error occurred. Please try again.')
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('main.index'))
