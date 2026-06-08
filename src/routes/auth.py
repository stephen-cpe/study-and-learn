"""
Authentication routes — signup, login, logout, password reset.
"""
from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from src import db
from src.models import User
from src.routes import bp


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
