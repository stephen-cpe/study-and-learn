"""
Route definitions for the Study-and-Learn MVP.
"""
import os
import json
import logging
import uuid
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app, jsonify, abort)
from src.utils import allowed_file
from src.services.document_parser import extract_text_with_vision
from src.services.summarizer import generate_summary
from src.services.relevance_checker import check_relevance
from src.services.curriculum_generator import generate_study_path
from src.services.rag_retriever import build_rag_context, build_rag_context_from_hashes
from src.services.vision_parser import hash_file, is_content_registered
from src.services.lesson_orchestrator import make_retriever, make_retriever_from_hashes, build_module_artifacts
from src.services.grader import _grade_single_question, _get_correct_answer
from src.services.exceptions import StudyAndLearnError
from src.repositories.lesson_repo import (
    get_lessons, save_lessons, get_extracted_texts, get_learning_goal,
    get_study_path_data, get_active_path, create_study_path,
    get_most_recent_active_path,
)
from src.services import progress_tracker
from flask_login import login_user, logout_user, login_required, current_user
from src.models import User, StudyPath, LessonProgress, ContentRegistry
from src import db

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx', 'pptx', 'png', 'jpg', 'jpeg'}
MAX_FILES = 5
PASS_THRESHOLD = 80


def _get_goal():
    """Return the current learning goal, preferring session, falling back to DB."""
    from_session = session.get('learning_goal', '')
    if from_session:
        return from_session
    path = get_most_recent_active_path(current_user)
    return path.learning_goal if path else ''


def _get_texts():
    """Return extracted texts, preferring session, falling back to DB."""
    texts = session.get('extracted_texts', [])
    if texts:
        return texts
    return get_extracted_texts(current_user) or []


def _get_hashes():
    """Return file hashes, preferring session, falling back to DB."""
    hashes = session.get('file_hashes', [])
    if hashes:
        return hashes
    path = get_most_recent_active_path(current_user)
    if path and path.file_hashes:
        try:
            return json.loads(path.file_hashes)
        except (json.JSONDecodeError, TypeError):
            pass
    return []


@bp.route('/')
def index():
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
        if allowed_file(file.filename):
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
                    if is_ajax:
                        progress_tracker.cleanup_task(task_id)
                        return jsonify({'error': f'Error extracting {filename}: {str(e)}'}), 400
                    flash(f'Error extracting {filename}: {str(e)}', 'error')
                    return redirect(url_for('main.index'))
                continue

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
                if is_ajax:
                    progress_tracker.cleanup_task(task_id)
                    return jsonify({'error': f'Error extracting {filename}: {str(e)}'}), 400
                flash(f'Error extracting {filename}: {str(e)}', 'error')
                return redirect(url_for('main.index'))
        else:
            if is_ajax:
                progress_tracker.cleanup_task(task_id)
                return jsonify({'error': f'Invalid file type: {file.filename}'}), 400
            flash(f'Skipping invalid file type: {file.filename}', 'warning')

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

        study_path = generate_study_path(goal, rag_context, summary)

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
                              file_hashes=file_hashes)

        if is_ajax:
            progress_tracker.update_progress(task_id, 8)
            progress_tracker.cleanup_task(task_id)
            return jsonify({'redirect': url_for('main.results')})

        flash(f'Processed {len(filenames)} file(s) successfully!', 'success')
        return redirect(url_for('main.results'))

    except StudyAndLearnError as e:
        logger.error("Processing failed: %s", str(e))
        if is_ajax:
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': str(e)}), 500
        flash(str(e), 'error')
        return redirect(url_for('main.index'))
    except Exception as e:
        logger.error("Unexpected processing error", exc_info=True)
        if is_ajax:
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': 'An unexpected error occurred. Please try again.'}), 500
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('main.index'))


@bp.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        abort(403)
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin.html', users=users)


@bp.route('/admin/toggle/<user_id>')
@login_required
def admin_toggle_generation(user_id):
    if not current_user.is_admin:
        abort(403)

    target = db.session.get(User, user_id)
    if not target:
        flash('User not found.', 'error')
        return redirect(url_for('main.admin'))

    target.can_generate_lessons = not target.can_generate_lessons
    db.session.commit()
    status = 'enabled' if target.can_generate_lessons else 'disabled'
    flash(f'Lesson generation {status} for {target.username}.', 'success')
    return redirect(url_for('main.admin'))


@bp.route('/admin/reset-password/<user_id>', methods=['POST'])
@login_required
def admin_reset_password(user_id):
    if not current_user.is_admin:
        abort(403)

    target = db.session.get(User, user_id)
    if not target:
        flash('User not found.', 'error')
        return redirect(url_for('main.admin'))

    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('main.admin'))

    target.set_password(new_password)
    db.session.commit()
    flash(f'Password reset for {target.username}.', 'success')
    return redirect(url_for('main.admin'))


@bp.route('/reset-password', methods=['GET', 'POST'])
@login_required
def reset_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('main.reset_password'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('Your password has been updated.', 'success')
        return redirect(url_for('main.index'))

    return render_template('reset_password.html')


# ── Error Handlers ──────────────────────────────────────────────────────

@bp.app_errorhandler(400)
def bad_request(e):
    return render_template('error.html', code=400,
                           message='Bad Request',
                           detail='The server could not understand the request.'), 400


@bp.app_errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403,
                           message='Access Denied',
                           detail='You do not have permission to access this page.'), 403


@bp.app_errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404,
                           message='Page Not Found',
                           detail='The page you are looking for does not exist.'), 404


@bp.app_errorhandler(500)
def internal_error(e):
    db.session.rollback()
    return render_template('error.html', code=500,
                           message='Internal Server Error',
                           detail='Something went wrong on our end. Please try again later.'), 500


@bp.route('/results')
def results():
    summary = session.get('summary', '')
    relevance_result = session.get('relevance_result', {})
    study_path = session.get('study_path', {})
    filename = session.get('processed_filename', 'unknown file')
    filenames = session.get('uploaded_filenames', [])
    learning_goal = session.get('learning_goal', '')

    if not summary and current_user.is_authenticated:
        goal = get_learning_goal(current_user)
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


@bp.route('/reset')
def reset():
    if current_user.is_authenticated:
        for path in StudyPath.query.filter_by(
            user_id=current_user.id, status='active'
        ).all():
            lesson_count = LessonProgress.query.filter_by(
                study_path_id=path.id
            ).count()
            if lesson_count == 0:
                path.status = 'cancelled'
        db.session.commit()
    session.clear()
    flash('Session reset. You can start over.', 'info')
    return redirect(url_for('main.index'))


@bp.route('/progress')
def progress():
    task_id = request.args.get('task_id', '') or session.sid
    status = progress_tracker.get_progress(task_id)
    if status is None:
        return jsonify({'stage': -1, 'label': 'No task', 'pct': 0, 'mascot': ''})
    return jsonify(status)


@bp.route('/generate-lessons', methods=['POST'])
@login_required
def generate_lessons():
    if not current_user.is_admin and not current_user.can_generate_lessons:
        flash('Lesson generation is disabled for your account. Contact an admin to enable access.', 'error')
        return redirect(url_for('main.dashboard'))

    learning_goal = session.get('learning_goal', '')
    study_path = session.get('study_path', {})

    if (not learning_goal or not study_path.get('modules')) and current_user.is_authenticated:
        learning_goal = get_learning_goal(current_user) or ''
        study_path = get_study_path_data(current_user) or {}

    if not learning_goal or not study_path.get('modules'):
        flash('No study path found. Please upload materials first.', 'error')
        return redirect(url_for('main.index'))

    active_count = current_user.active_lesson_count
    existing_path = get_active_path(current_user)
    if existing_path is None and active_count >= 3:
        flash('You already have 3 active lessons. Complete or abandon one before starting a new one.', 'error')
        return redirect(url_for('main.dashboard'))

    body = request.get_json(silent=True) or {}
    task_id = body.get('task_id', '') or session.sid
    progress_tracker.create_task(task_id=task_id)

    modules = study_path['modules']

    most_recent = get_most_recent_active_path(current_user)
    path_id_val = most_recent.id if most_recent else None
    lessons = get_lessons(current_user, path_id=path_id_val)

    extracted_texts = _get_texts()
    file_hashes_data = _get_hashes()
    if file_hashes_data:
        retriever = make_retriever_from_hashes(learning_goal, file_hashes_data)
    else:
        retriever = make_retriever(learning_goal, extracted_texts)

    progress_tracker.update_progress(task_id, 1)

    for i, module in enumerate(modules):
        progress_tracker.update_progress(task_id, 2)
        artifacts = build_module_artifacts(module, learning_goal, retriever)
        progress_tracker.update_progress(task_id, 3)

        lessons.append({
            'index': i,
            'module_title': module['title'],
            'estimated_effort': module.get('estimated_effort', 'N/A'),
            'lesson': artifacts['lesson'],
            'quiz': artifacts['quiz'],
            'checkpoints': artifacts['checkpoints'],
            'completed': False,
            'score': None,
            'passed': False
        })

    progress_tracker.update_progress(task_id, 4)

    save_lessons(lessons, current_user,
                 title=study_path.get('title', learning_goal[:50]),
                 learning_goal=learning_goal,
                 extracted_texts=extracted_texts,
                 file_hashes_val=file_hashes_data,
                 path_id=path_id_val)

    flash(f'Generated {len(modules)} lessons successfully!', 'success')
    return jsonify({'redirect': url_for('main.lessons', path_id=path_id_val)})


@bp.route('/lessons')
@login_required
def lessons():
    path_id = request.args.get('path_id', None)
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        flash('No lessons generated yet. Generate lessons from your results first.', 'info')
        return redirect(url_for('main.results'))

    for i, lesson in enumerate(lessons_data):
        lesson['unlocked'] = True
        if i > 0:
            prev = lessons_data[i - 1]
            if not prev.get('passed', False):
                lesson['unlocked'] = False

    return render_template('lessons.html',
                           lessons=lessons_data,
                           pass_threshold=PASS_THRESHOLD,
                           path_id=path_id)


@bp.route('/lessons/<int:module_index>')
@login_required
def lesson_deck(module_index):
    path_id = request.args.get('path_id', None)
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        flash('No lessons generated yet.', 'error')
        return redirect(url_for('main.results'))

    if module_index < 0 or module_index >= len(lessons_data):
        flash('Invalid module index.', 'error')
        return redirect(url_for('main.lessons'))

    if module_index > 0:
        prev = lessons_data[module_index - 1]
        if not prev.get('passed', False):
            flash('You must pass the previous module before accessing this one.', 'warning')
            return redirect(url_for('main.lessons'))

    lesson = lessons_data[module_index]
    return render_template('lesson_deck.html',
                           lesson=lesson,
                           module_index=module_index,
                           total_modules=len(lessons_data),
                           pass_threshold=PASS_THRESHOLD,
                           path_id=path_id)


@bp.route('/lessons/<int:module_index>/grade', methods=['POST'])
@login_required
def grade_lesson(module_index):
    path_id = request.args.get('path_id', None)
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        return jsonify({'error': 'No lessons found'}), 404

    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    data = request.get_json(silent=True) or {}
    answers = data.get('answers', [])
    fill_blank_answers = data.get('fill_blank_answers', {})

    quiz_questions = lesson.get('quiz', {}).get('questions', [])
    checkpoints = lesson.get('checkpoints', {})
    checkpoint_answers = data.get('checkpoint_answers', {})

    total_points = len(quiz_questions) + len(checkpoints)
    earned_points = 0
    quiz_results = []

    for i, question in enumerate(quiz_questions):
        if question['type'] == 'fill_blank':
            user_answer = fill_blank_answers.get(question['id'], answers[i] if i < len(answers) else None)
        else:
            user_answer = answers[i] if i < len(answers) else None
        correct = _grade_single_question(question, user_answer)
        if correct:
            earned_points += 1
        quiz_results.append({
            'id': question['id'],
            'type': question['type'],
            'prompt': question['prompt'],
            'user_answer': user_answer,
            'correct_answer': _get_correct_answer(question),
            'correct': correct,
            'explanation': question.get('explanation', '')
        })

    checkpoint_results = []
    for slide_idx, cp in checkpoints.items():
        user_cp = checkpoint_answers.get(slide_idx)
        cp_correct = _grade_single_question(cp, user_cp)
        if cp_correct:
            earned_points += 1
        checkpoint_results.append({
            'slide_index': slide_idx,
            'prompt': cp.get('prompt', ''),
            'user_answer': user_cp,
            'correct_answer': _get_correct_answer(cp),
            'correct': cp_correct,
            'explanation': cp.get('explanation', '')
        })

    if total_points == 0:
        total_points = 1
    score_pct = round((earned_points / total_points) * 100)
    passed = score_pct >= PASS_THRESHOLD

    lessons_data[module_index]['completed'] = True
    lessons_data[module_index]['score'] = score_pct
    lessons_data[module_index]['passed'] = passed
    save_lessons(lessons_data, current_user, path_id=path_id)

    return jsonify({
        'score': score_pct,
        'passed': passed,
        'threshold': PASS_THRESHOLD,
        'earned': earned_points,
        'total': total_points,
        'quiz_results': quiz_results,
        'checkpoint_results': checkpoint_results
    })


@bp.route('/lessons/<int:module_index>/retake', methods=['POST'])
@login_required
def retake_lesson(module_index):
    path_id = request.args.get('path_id', None)
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        return jsonify({'error': 'No lessons found'}), 404

    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    module_title = lesson.get('module_title', '')
    slides = lesson.get('lesson', {}).get('slides', [])
    learning_goal = _get_goal()
    extracted_texts = _get_texts()
    file_hashes_data = _get_hashes()

    if file_hashes_data:
        retriever = make_retriever_from_hashes(learning_goal, file_hashes_data)
    else:
        retriever = make_retriever(learning_goal, extracted_texts)

    artifacts = build_module_artifacts(
        {'title': module_title},
        learning_goal,
        retriever,
        existing_slides=slides,
    )

    lessons_data[module_index]['quiz'] = artifacts['quiz']
    lessons_data[module_index]['checkpoints'] = artifacts['checkpoints']
    lessons_data[module_index]['completed'] = False
    lessons_data[module_index]['score'] = None
    lessons_data[module_index]['passed'] = False
    save_lessons(lessons_data, current_user, path_id=path_id)

    return jsonify({'success': True})


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('main.signup'))

        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return redirect(url_for('main.signup'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('main.signup'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Account created successfully!', 'success')
        return redirect(url_for('main.index'))

    return render_template('signup.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            for key in ('learning_goal', 'summary', 'relevance_result',
                        'study_path', 'processed_filename', 'uploaded_filenames',
                        'extracted_texts', 'file_hashes'):
                session.pop(key, None)
            login_user(user, remember=True)
            flash('Welcome back!', 'success')
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.index'))

        flash('Invalid username or password.', 'error')
        return redirect(url_for('main.index'))


@bp.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))


@bp.route('/dashboard')
@login_required
def dashboard():
    active_paths = StudyPath.query.filter_by(
        user_id=current_user.id, status='active'
    ).order_by(StudyPath.created_at.desc()).all()

    paths_data = []
    for path in active_paths:
        progress_rows = LessonProgress.query.filter_by(
            study_path_id=path.id
        ).all()
        total_modules = len(progress_rows)
        completed_modules = sum(1 for r in progress_rows if r.passed)
        pct = (
            round((completed_modules / total_modules) * 100)
            if total_modules > 0 else 0
        )
        paths_data.append({
            'id': path.id,
            'title': path.title,
            'learning_goal': path.learning_goal,
            'created_at': path.created_at,
            'total_modules': total_modules,
            'completed_modules': completed_modules,
            'progress_pct': pct,
        })

    return render_template(
        'dashboard.html',
        paths=paths_data,
        at_cap=current_user.active_lesson_count >= 3,
    )


@bp.route('/study-path/<path_id>/cancel', methods=['POST'])
@login_required
def cancel_study_path(path_id):
    path = StudyPath.query.filter_by(id=path_id, user_id=current_user.id).first()
    if not path:
        flash('Study path not found.', 'error')
        return redirect(url_for('main.dashboard'))

    path.status = 'cancelled'
    db.session.commit()
    flash(f'"{path.title}" has been cancelled.', 'success')
    return redirect(url_for('main.dashboard'))


@bp.route('/seed-demo')
@login_required
def seed_demo():
    if not current_user.is_admin:
        abort(403)

    created = []
    for username, password in [('alice', 'demo123'), ('bob', 'demo123')]:
        existing = User.query.filter_by(username=username).first()
        if not existing:
            user = User(username=username, email=f'{username}@example.com',
                        can_generate_lessons=True)
            user.set_password(password)
            db.session.add(user)
            created.append(username)

    if created:
        db.session.commit()
        flash(f'Demo accounts seeded: {", ".join(created)}.', 'success')
    else:
        flash('Demo accounts already exist.', 'info')

    return redirect(url_for('main.admin'))
