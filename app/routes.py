"""
Route definitions for the Study-and-Learn MVP.
"""
import os
import uuid
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, current_app, jsonify)
from app.utils import allowed_file
from app.services.document_parser import extract_text
from app.services.summarizer import generate_summary
from app.services.relevance_checker import check_relevance
from app.services.curriculum_generator import generate_study_path
from app.services.rag_retriever import build_rag_context
from app.services.lesson_generator import generate_lesson
from app.services.quiz_generator import generate_quiz, generate_inline_checkpoint

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'txt', 'md', 'pdf', 'docx'}
MAX_FILES = 5
PASS_THRESHOLD = 80


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/process', methods=['POST'])
def process():
    goal = request.form.get('learning_goal', '').strip()
    files = request.files.getlist('files')
    valid_files = [f for f in files if f and f.filename and f.filename.strip()]

    if not goal:
        flash('Please enter a learning goal', 'error')
        return redirect(url_for('main.index'))

    if not valid_files:
        flash('No valid files selected', 'error')
        return redirect(url_for('main.index'))

    if len(valid_files) > MAX_FILES:
        flash(f'Maximum {MAX_FILES} files allowed', 'error')
        return redirect(url_for('main.index'))

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
                flash(f'Error extracting {filename}: {str(e)}', 'error')
                return redirect(url_for('main.index'))
        else:
            flash(f'Skipping invalid file type: {file.filename}', 'warning')

    if not extracted_texts:
        flash('No valid files to process', 'error')
        return redirect(url_for('main.index'))

    try:
        rag_context = build_rag_context(goal, extracted_texts)
        if not rag_context:
            rag_context = "\n\n".join(extracted_texts)

        summary = generate_summary(rag_context)
        relevance_result = check_relevance(goal, rag_context, summary)
        study_path = generate_study_path(goal, rag_context, summary)

        session['learning_goal'] = goal
        session['summary'] = summary
        session['relevance_result'] = relevance_result
        session['study_path'] = study_path
        session['processed_filename'] = ', '.join(filenames)
        session['uploaded_filenames'] = filenames
        session['extracted_texts'] = extracted_texts

        flash(f'Processed {len(filenames)} file(s) successfully!', 'success')
        return redirect(url_for('main.results'))

    except Exception as e:
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


@bp.route('/generate-lessons', methods=['POST'])
def generate_lessons():
    learning_goal = session.get('learning_goal', '')
    study_path = session.get('study_path', {})

    if not learning_goal or not study_path.get('modules'):
        flash('No study path found. Please upload materials first.', 'error')
        return redirect(url_for('main.index'))

    modules = study_path['modules']
    lessons = session.get('lessons', [])

    extracted_texts = session.get('extracted_texts', [])

    def make_retriever(goal):
        def retrieve(query):
            return build_rag_context(goal, extracted_texts) if extracted_texts else ""
        return retrieve

    retriever = make_retriever(learning_goal)

    for i, module in enumerate(modules):
        lesson_data = generate_lesson(module['title'], learning_goal, retriever)
        quiz_data = generate_quiz(module['title'], lesson_data.get('slides', []), retriever, n_questions=5)

        checkpoint_count = 0
        slides = lesson_data.get('slides', [])
        checkpoints = {}
        if len(slides) > 2:
            interval = max(1, len(slides) // 3)
            for idx in range(interval - 1, len(slides) - 1, interval):
                slides_subset = slides[max(0, idx - 1):idx + 1]
                cp = generate_inline_checkpoint(module['title'], slides_subset, retriever)
                checkpoints[str(idx)] = cp
                checkpoint_count += 1
            if len(slides) > 1:
                last_checkpoint_slide = max(0, len(slides) - 2)
                if str(last_checkpoint_slide) not in checkpoints:
                    slides_subset = slides[max(0, last_checkpoint_slide - 1):last_checkpoint_slide + 1]
                    cp = generate_inline_checkpoint(module['title'], slides_subset, retriever)
                    checkpoints[str(last_checkpoint_slide)] = cp

        lessons.append({
            'index': i,
            'module_title': module['title'],
            'estimated_effort': module.get('estimated_effort', 'N/A'),
            'lesson': lesson_data,
            'quiz': quiz_data,
            'checkpoints': checkpoints,
            'completed': False,
            'score': None,
            'passed': False
        })

    session['lessons'] = lessons
    session.modified = True

    flash(f'Generated {len(modules)} lessons successfully!', 'success')
    return redirect(url_for('main.lessons'))


@bp.route('/lessons')
def lessons():
    if 'lessons' not in session:
        flash('No lessons generated yet. Generate lessons from your results first.', 'info')
        return redirect(url_for('main.results'))

    lessons_data = session.get('lessons', [])

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
    if 'lessons' not in session:
        flash('No lessons generated yet.', 'error')
        return redirect(url_for('main.results'))

    lessons_data = session.get('lessons', [])

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
    if 'lessons' not in session:
        return jsonify({'error': 'No lessons found'}), 404

    lessons_data = session.get('lessons', [])
    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    data = request.get_json(silent=True) or {}
    answers = data.get('answers', [])

    quiz_questions = lesson.get('quiz', {}).get('questions', [])
    checkpoints = lesson.get('checkpoints', {})
    checkpoint_answers = data.get('checkpoint_answers', {})

    total_points = len(quiz_questions) + len(checkpoints)
    earned_points = 0
    quiz_results = []

    for i, question in enumerate(quiz_questions):
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
    session['lessons'] = lessons_data
    session.modified = True

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
    if 'lessons' not in session:
        return jsonify({'error': 'No lessons found'}), 404

    lessons_data = session.get('lessons', [])
    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    module_title = lesson.get('module_title', '')
    slides = lesson.get('lesson', {}).get('slides', [])
    learning_goal = session.get('learning_goal', '')
    extracted_texts = session.get('extracted_texts', [])

    def make_retriever(goal):
        def retrieve(query):
            return build_rag_context(goal, extracted_texts) if extracted_texts else ""
        return retrieve

    retriever = make_retriever(learning_goal)

    new_quiz = generate_quiz(module_title, slides, retriever, n_questions=5)
    new_checkpoints = {}
    if len(slides) > 2:
        interval = max(1, len(slides) // 3)
        for idx in range(interval - 1, len(slides) - 1, interval):
            slides_subset = slides[max(0, idx - 1):idx + 1]
            cp = generate_inline_checkpoint(module_title, slides_subset, retriever)
            new_checkpoints[str(idx)] = cp
        if len(slides) > 1:
            last_checkpoint_slide = max(0, len(slides) - 2)
            if str(last_checkpoint_slide) not in new_checkpoints:
                slides_subset = slides[max(0, last_checkpoint_slide - 1):last_checkpoint_slide + 1]
                cp = generate_inline_checkpoint(module_title, slides_subset, retriever)
                new_checkpoints[str(last_checkpoint_slide)] = cp

    lessons_data[module_index]['quiz'] = new_quiz
    lessons_data[module_index]['checkpoints'] = new_checkpoints
    lessons_data[module_index]['completed'] = False
    lessons_data[module_index]['score'] = None
    lessons_data[module_index]['passed'] = False
    session['lessons'] = lessons_data
    session.modified = True

    return jsonify({'success': True})


def _grade_single_question(question: dict, user_answer) -> bool:
    qtype = question.get('type', '')
    if qtype == 'mcq':
        return user_answer is not None and int(user_answer) == question.get('answer_index', -1)
    elif qtype == 'true_false':
        if isinstance(user_answer, str):
            user_answer = user_answer.lower() in ('true', '1', 'yes')
        return bool(user_answer) == bool(question.get('answer', False))
    elif qtype == 'multi_select':
        if not isinstance(user_answer, list):
            user_answer = [int(user_answer)] if user_answer is not None else []
        correct = question.get('answer_indices', [])
        return set(int(x) for x in user_answer) == set(correct)
    elif qtype == 'fill_blank':
        if not isinstance(user_answer, str):
            return False
        acceptable = question.get('acceptable_answers', [question.get('answer', '')])
        return user_answer.strip().lower() in [a.strip().lower() for a in acceptable]
    return False


def _get_correct_answer(question: dict):
    qtype = question.get('type', '')
    if qtype == 'mcq':
        return question.get('answer_index')
    elif qtype == 'true_false':
        return question.get('answer')
    elif qtype == 'multi_select':
        return question.get('answer_indices')
    elif qtype == 'fill_blank':
        return question.get('answer')
    return None
