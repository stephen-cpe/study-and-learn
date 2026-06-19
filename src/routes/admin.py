"""
Admin routes — user management.
"""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from src import db
from src.models import User
from src.routes import bp


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



