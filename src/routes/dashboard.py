"""
Dashboard routes — user dashboard, path cancellation, and session reset.
"""
import io
import json
import logging
from datetime import datetime, timezone

from flask import (Response, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

from src import db
from src.models import LessonProgress, StudyPath
from src.routes import bp


@bp.route('/dashboard')
@login_required
def dashboard():
    tab = request.args.get('tab', 'active')

    def _build_paths(status_filter):
        paths = StudyPath.query.filter_by(
            user_id=current_user.id, status=status_filter
        ).order_by(StudyPath.created_at.desc()).all()

        result = []
        for path in paths:
            progress_rows = LessonProgress.query.filter_by(
                study_path_id=path.id
            ).all()
            total_modules = len(progress_rows)
            passed_modules = sum(1 for r in progress_rows if r.passed)
            pct = (
                round((passed_modules / total_modules) * 100)
                if total_modules > 0 else 0
            )
            scores = [r.score for r in progress_rows if r.score is not None]
            avg_score = round(sum(scores) / len(scores)) if scores else None
            result.append({
                'id': path.id,
                'title': path.title,
                'learning_goal': path.learning_goal,
                'status': path.status,
                'created_at': path.created_at,
                'updated_at': path.updated_at,
                'total_modules': total_modules,
                'completed_modules': passed_modules,
                'progress_pct': pct,
                'avg_score': avg_score,
                'all_passed': passed_modules == total_modules and total_modules > 0,
            })
        return result

    active_paths = _build_paths('active')
    completed_paths = _build_paths('completed')
    cancelled_paths = _build_paths('cancelled')

    return render_template(
        'dashboard.html',
        active_paths=active_paths,
        completed_paths=completed_paths,
        cancelled_paths=cancelled_paths,
        tab=tab,
        at_cap=current_user.active_lesson_count >= 3,
    )


@bp.route('/study-path/<path_id>/complete', methods=['POST'])
@login_required
def complete_study_path(path_id):
    path = StudyPath.query.filter_by(id=path_id, user_id=current_user.id).first()
    if not path:
        flash('Study path not found.', 'error')
        return redirect(url_for('main.dashboard'))

    progress_rows = LessonProgress.query.filter_by(study_path_id=path.id).all()
    if not progress_rows or not all(r.passed for r in progress_rows):
        flash('All modules must be passed before marking as complete.', 'error')
        return redirect(url_for('main.dashboard'))

    path.status = 'completed'
    path.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    try:
        from src.services.tts_service import delete_lesson_audio
        delete_lesson_audio(path_id)
    except Exception as e:
        logger.warning("TTS cleanup failed for path %s: %s", path_id, str(e))
    flash(f'"{path.title}" marked as complete!', 'success')
    return redirect(url_for('main.dashboard'))


@bp.route('/study-path/<path_id>/cancel', methods=['POST'])
@login_required
def cancel_study_path(path_id):
    path = StudyPath.query.filter_by(id=path_id, user_id=current_user.id).first()
    if not path:
        flash('Study path not found.', 'error')
        return redirect(url_for('main.dashboard'))

    path.status = 'cancelled'
    db.session.commit()
    try:
        from src.services.tts_service import delete_lesson_audio
        delete_lesson_audio(path_id)
    except Exception as e:
        logger.warning("TTS cleanup failed for path %s: %s", path_id, str(e))
    flash(f'"{path.title}" has been cancelled.', 'success')
    return redirect(url_for('main.dashboard'))


@bp.route('/study-path/<path_id>/delete', methods=['POST'])
@login_required
def delete_study_path(path_id):
    path = StudyPath.query.filter_by(id=path_id, user_id=current_user.id).first()
    if not path:
        flash('Study path not found.', 'error')
        return redirect(url_for('main.dashboard'))

    if path.status not in ('completed', 'cancelled'):
        flash('Only completed or cancelled lessons can be deleted.', 'error')
        return redirect(url_for('main.dashboard'))

    title = path.title
    LessonProgress.query.filter_by(study_path_id=path.id).delete()
    db.session.delete(path)
    db.session.commit()
    try:
        from src.services.tts_service import delete_lesson_audio
        delete_lesson_audio(path_id)
    except Exception as e:
        logger.warning("TTS cleanup failed for path %s: %s", path_id, str(e))
    flash(f'"{title}" has been permanently deleted.', 'success')
    return redirect(url_for('main.dashboard'))


@bp.route('/lessons/<int:module_index>/export')
@login_required
def export_lesson_pdf(module_index):
    from src.repositories.lesson_repo import get_lessons

    path_id = request.args.get('path_id', None)
    lessons_data = get_lessons(current_user, path_id=path_id)

    if not lessons_data:
        flash('No lessons found.', 'error')
        return redirect(url_for('main.dashboard'))

    if module_index < 0 or module_index >= len(lessons_data):
        flash('Invalid module index.', 'error')
        return redirect(url_for('main.dashboard'))

    lesson = lessons_data[module_index]
    if not lesson.get('passed', False):
        flash('You can only export lessons you have passed.', 'error')
        return redirect(url_for('main.lessons', path_id=path_id))

    slides = lesson.get('lesson', {}).get('slides', [])
    quiz_questions = lesson.get('quiz', {}).get('questions', [])
    checkpoints = lesson.get('checkpoints', {})
    sources = lesson.get('sources', [])

    now = datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')
    score = lesson.get('score', 'N/A')

    pdf_bytes = _build_pdf(lesson, slides, quiz_questions, checkpoints, sources, score, now)

    safe_title = lesson.get('module_title', 'lesson')
    safe_title = _clean_filename(safe_title)
    safe_title = safe_title.replace(' ', '_').replace('/', '_')
    filename = f"{safe_title}.pdf"
    return Response(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


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


def _clean_filename(name: str) -> str:
    import unicodedata
    result = []
    s = unicodedata.normalize('NFKD', str(name))
    for ch in s:
        if 32 <= ord(ch) < 127:
            result.append(ch)
        elif ord(ch) < 256:
            result.append(ch)
        elif ch == '\u2013':
            result.append('-')
        elif ch == '\u2014':
            result.append('--')
        elif ch in ('\u2018', '\u2019'):
            result.append("'")
        elif ch in ('\u201c', '\u201d'):
            result.append('"')
    cleaned = ''.join(result).strip()
    return cleaned or 'lesson'


def _build_pdf(lesson, slides, quiz_questions, checkpoints, sources, score, now) -> bytes:
    from fpdf import FPDF
    import unicodedata

    def _clean(text):
        s = str(text)
        s = unicodedata.normalize('NFKD', s)
        result = []
        for ch in s:
            cat = unicodedata.category(ch)
            if cat.startswith('M'):
                continue
            if ord(ch) < 256:
                result.append(ch)
            elif ch == '\u2013':
                result.append('-')
            elif ch == '\u2014':
                result.append('--')
            elif ch in ('\u2018', '\u2019', '\u201a', '\u201b'):
                result.append("'")
            elif ch in ('\u201c', '\u201d', '\u201e', '\u201f'):
                result.append('"')
            elif ch == '\u2026':
                result.append('...')
            elif ch == '\u2022':
                result.append('-')
            elif ch == '\u00a0':
                result.append(' ')
            else:
                result.append('?')
        return ''.join(result)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(0, 180, 216)
    pdf.cell(0, 12, 'Study-and-Learn', ln=True, align='C')
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(10, 22, 40)
    module_title = _clean(lesson.get('module_title', 'Lesson'))
    pdf.multi_cell(0, 8, module_title, align='C')
    pdf.ln(3)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(102, 102, 102)
    effort = _clean(lesson.get('estimated_effort', 'N/A'))
    pdf.cell(0, 6, f'Estimated effort: {effort}    Score: {score}%    PASSED', ln=True, align='C')
    pdf.cell(0, 6, f'Generated: {now}', ln=True, align='C')
    pdf.ln(6)

    def _section_header(title):
        pdf.set_draw_color(224, 224, 224)
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(10, y, 200, y)
        pdf.ln(3)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(0, 180, 216)
        pdf.cell(0, 8, title, ln=True)
        pdf.ln(2)

    _section_header('Lesson Slides')
    for slide in slides:
        stype = slide.get('type', '')
        pdf.ln(1)
        if stype == 'title':
            pdf.set_font('Helvetica', 'B', 13)
            pdf.set_text_color(0, 180, 216)
            pdf.cell(0, 7, _clean(slide.get('title', '')), ln=True, align='C')
            sub = _clean(slide.get('subtitle', ''))
            if sub:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(136, 136, 136)
                pdf.cell(0, 6, sub, ln=True, align='C')
        elif stype == 'content':
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(10, 22, 40)
            pdf.cell(0, 7, _clean(slide.get('heading', '')), ln=True)
            for b in slide.get('bullets', []):
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(26, 26, 46)
                pdf.set_x(15)
                pdf.cell(5, 5.5, '-')
                pdf.multi_cell(170, 5.5, _clean(b))
            notes = slide.get('notes', '')
            if notes:
                pdf.set_font('Helvetica', 'I', 9)
                pdf.set_text_color(102, 102, 102)
                pdf.set_x(15)
                pdf.multi_cell(175, 5, _clean(notes))
        elif stype == 'example':
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(10, 22, 40)
            pdf.cell(0, 7, _clean(slide.get('heading', '')), ln=True)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(26, 26, 46)
            pdf.set_x(15)
            pdf.multi_cell(175, 5.5, _clean(slide.get('body', '')))
        elif stype == 'summary':
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(0, 180, 216)
            pdf.cell(0, 7, 'Summary', ln=True)
            for b in slide.get('bullets', []):
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(26, 26, 46)
                pdf.set_x(15)
                pdf.cell(5, 5.5, '-')
                pdf.multi_cell(170, 5.5, _clean(b))
        pdf.ln(2)

    if checkpoints:
        _section_header('Inline Checkpoints')
        for si, cp in checkpoints.items():
            pdf.set_x(pdf.l_margin)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(0, 180, 216)
            slide_num = int(si) + 1
            pdf.cell(0, 5.5, f'Checkpoint (after slide {slide_num})', ln=True)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(26, 26, 46)
            pdf.multi_cell(0, 5.5, _clean(cp.get('prompt', '')))
            options = cp.get('options', [])
            ans_idx = cp.get('answer_index', 0)
            if 0 <= ans_idx < len(options):
                pdf.set_x(pdf.l_margin)
                pdf.set_font('Helvetica', 'B', 9)
                pdf.set_text_color(22, 163, 74)
                pdf.cell(0, 5.5, _clean(f'Answer: {options[ans_idx]}'), ln=True)
            pdf.ln(2)

    if quiz_questions:
        _section_header('Final Quiz')
        for q in quiz_questions:
            qtype = q.get('type', '')
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(10, 22, 40)
            type_label = ' (Select all)' if qtype == 'multi_select' else ''
            pdf.multi_cell(0, 5.5, _clean(f'Q: {q.get("prompt", "")}{type_label}'))
            answer_text = ''
            if qtype == 'mcq':
                opts = q.get('options', [])
                idx = q.get('answer_index', 0)
                if 0 <= idx < len(opts):
                    answer_text = opts[idx]
            elif qtype == 'true_false':
                answer_text = 'True' if q.get('answer') else 'False'
            elif qtype == 'multi_select':
                opts = q.get('options', [])
                indices = q.get('answer_indices', [])
                answer_text = ', '.join(opts[i] for i in indices if 0 <= i < len(opts))
            elif qtype == 'cloze_dropdown':
                opts = q.get('options', [])
                idx = q.get('answer_index', 0)
                if 0 <= idx < len(opts):
                    answer_text = opts[idx]
            elif qtype == 'fill_blank':
                if 'options' in q and 'answer_index' in q:
                    opts = q.get('options', [])
                    idx = q.get('answer_index', 0)
                    if 0 <= idx < len(opts):
                        answer_text = opts[idx]
                else:
                    answer_text = str(q.get('answer', ''))
            if answer_text:
                pdf.set_x(pdf.l_margin)
                pdf.set_font('Helvetica', 'B', 9)
                pdf.set_text_color(22, 163, 74)
                pdf.cell(0, 5.5, _clean(f'Answer: {answer_text}'), ln=True)
            explanation = q.get('explanation', '')
            if explanation:
                pdf.set_font('Helvetica', 'I', 9)
                pdf.set_text_color(102, 102, 102)
                pdf.multi_cell(0, 5, _clean(explanation))
            pdf.ln(2)

    if sources:
        _section_header('Source Materials')
        for src in sources:
            filename = src.get('filename', 'Unknown')
            text = src.get('text', '')
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(0, 180, 216)
            pdf.cell(0, 5.5, _clean(filename), ln=True)
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(85, 85, 85)
            pdf.multi_cell(0, 5, _clean(text))
            pdf.ln(2)

    pdf.ln(8)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(153, 153, 153)
    pdf.cell(0, 5, f'Generated by Study-and-Learn on {now}', ln=True, align='C')

    return pdf.output()
