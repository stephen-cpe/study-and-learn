"""
Route definitions for the Study-and-Learn MVP.
"""
import os
import uuid
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app, jsonify)
from src.utils import allowed_file
from src.services.document_parser import extract_text
from src.services.summarizer import generate_summary
from src.services.relevance_checker import check_relevance
from src.services.curriculum_generator import generate_study_path
from src.services.rag_retriever import build_rag_context
from src.services.lesson_orchestrator import make_retriever, build_module_artifacts
from src.services.grader import _grade_single_question, _get_correct_answer
from src.repositories.session_repo import get_lessons, save_lessons
from src.services import progress_tracker
from flask_login import login_user, logout_user
from src.models import User
from src import db

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx'}
MAX_FILES = 5
PASS_THRESHOLD = 80


@bp.route('/')
def index():
    return render_template('index.html')


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

    for file in valid_files:
        if allowed_file(file.filename):
            filename = file.filename
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            try:
                text = extract_text(file_path)
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
            progress_tracker.update_progress(task_id, 0)

        rag_context = build_rag_context(goal, extracted_texts)
        if not rag_context:
            rag_context = "\n\n".join(extracted_texts)

        if is_ajax:
            progress_tracker.update_progress(task_id, 1)

        if is_ajax:
            progress_tracker.update_progress(task_id, 2)

        summary = generate_summary(rag_context)
        if is_ajax:
            progress_tracker.update_progress(task_id, 3)

        relevance_result = check_relevance(goal, rag_context, summary)
        if is_ajax:
            progress_tracker.update_progress(task_id, 4)

        study_path = generate_study_path(goal, rag_context, summary)
        if is_ajax:
            progress_tracker.update_progress(task_id, 5)

        session['learning_goal'] = goal
        session['summary'] = summary
        session['relevance_result'] = relevance_result
        session['study_path'] = study_path
        session['processed_filename'] = ', '.join(filenames)
        session['uploaded_filenames'] = filenames
        session['extracted_texts'] = extracted_texts

        if is_ajax:
            progress_tracker.update_progress(task_id, 6)
            progress_tracker.cleanup_task(task_id)
            return jsonify({'redirect': url_for('main.results')})

        flash(f'Processed {len(filenames)} file(s) successfully!', 'success')
        return redirect(url_for('main.results'))

    except Exception as e:
        if is_ajax:
            progress_tracker.cleanup_task(task_id)
            return jsonify({'error': str(e)}), 500
        flash(f'Processing error: {str(e)}', 'error')
        return redirect(url_for('main.index'))


@bp.route('/results')
def results():
    if 'summary' not in session:
        flash('No results to display. Please upload a file first.', 'info')
        return redirect(url_for('main.index'))

    summary = session.get('summary', '')
    relevance_result = session.get('relevance_result', {})
    study_path = session.get('study_path', {})
    filename = session.get('processed_filename', 'unknown file')
    filenames = session.get('uploaded_filenames', [])
    learning_goal = session.get('learning_goal', '')

    return render_template('results.html',
                           summary=summary,
                           relevance_result=relevance_result,
                           study_path=study_path,
                           filename=filename,
                           filenames=filenames,
                           learning_goal=learning_goal)


@bp.route('/reset')
def reset():
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
def generate_lessons():
    learning_goal = session.get('learning_goal', '')
    study_path = session.get('study_path', {})

    if not learning_goal or not study_path.get('modules'):
        flash('No study path found. Please upload materials first.', 'error')
        return redirect(url_for('main.index'))

    body = request.get_json(silent=True) or {}
    task_id = body.get('task_id', '') or session.sid
    progress_tracker.create_task(task_id=task_id)

    modules = study_path['modules']
    lessons = get_lessons()

    extracted_texts = session.get('extracted_texts', [])
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

    save_lessons(lessons)

    flash(f'Generated {len(modules)} lessons successfully!', 'success')
    return redirect(url_for('main.lessons'))


@bp.route('/lessons')
def lessons():
    lessons_data = get_lessons()
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
                           pass_threshold=PASS_THRESHOLD)


@bp.route('/lessons/<int:module_index>')
def lesson_deck(module_index):
    lessons_data = get_lessons()
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
                           pass_threshold=PASS_THRESHOLD)


@bp.route('/lessons/<int:module_index>/grade', methods=['POST'])
def grade_lesson(module_index):
    lessons_data = get_lessons()
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
    save_lessons(lessons_data)

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
def retake_lesson(module_index):
    lessons_data = get_lessons()
    if not lessons_data:
        return jsonify({'error': 'No lessons found'}), 404

    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    module_title = lesson.get('module_title', '')
    slides = lesson.get('lesson', {}).get('slides', [])
    learning_goal = session.get('learning_goal', '')
    extracted_texts = session.get('extracted_texts', [])

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
    save_lessons(lessons_data)

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
            login_user(user, remember=True)
            flash('Welcome back!', 'success')
            return redirect(url_for('main.index'))

        flash('Invalid username or password.', 'error')
        return redirect(url_for('main.login'))

    return render_template('login.html')


@bp.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))
