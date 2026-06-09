"""
Lesson routes — generation, slide deck, grading, and retake.
"""
from flask import (flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_login import current_user, login_required

from src.repositories.lesson_repo import (
    get_active_path,
    get_learning_goal as _db_get_goal,
    get_lessons,
    get_most_recent_active_path,
    get_study_path_data,
    save_lessons,
)
from src.routes import PASS_THRESHOLD, bp
from src.routes._helpers import _build_retriever, _resolve_goal, _resolve_hashes, _resolve_texts, _resolve_filenames
from src.services import progress_tracker
from src.services.grader import _get_correct_answer, _grade_single_question
from src.services.lesson_orchestrator import build_module_artifacts


@bp.route('/generate-lessons', methods=['POST'])
@login_required
def generate_lessons():
    if not current_user.is_admin and not current_user.can_generate_lessons:
        flash('Lesson generation is disabled for your account. Contact an admin to enable access.', 'error')
        return redirect(url_for('main.dashboard'))

    learning_goal = session.get('learning_goal', '')
    study_path = session.get('study_path', {})

    if (not learning_goal or not study_path.get('modules')) and current_user.is_authenticated:
        learning_goal = _db_get_goal(current_user) or ''
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

    extracted_texts = _resolve_texts()
    file_hashes_data = _resolve_hashes()
    file_names_data = _resolve_filenames()
    retriever = _build_retriever(learning_goal, extracted_texts, file_hashes_data, file_names_data)

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
            'sources': artifacts.get('sources', []),
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
                 file_names_val=file_names_data,
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
    goal = _resolve_goal()
    texts = _resolve_texts()
    hashes_data = _resolve_hashes()
    names_data = _resolve_filenames()
    retriever = _build_retriever(goal, texts, hashes_data, names_data)

    artifacts = build_module_artifacts(
        {'title': module_title},
        goal,
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
