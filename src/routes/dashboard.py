"""
Dashboard routes — user dashboard, path cancellation, and session reset.
"""
from flask import flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required

from src import db
from src.models import LessonProgress, StudyPath
from src.routes import bp


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
