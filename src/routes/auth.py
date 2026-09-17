"""
Authentication routes — signup, login, logout, password reset.
"""
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from src import db
from src.models import User
from src.routes import bp
from src.services.settings_service import (
    ALLOWED_AVATARS,
    DEFAULT_DIFFICULTY,
    DIFFICULTY_LEVELS,
    TTS_SPEAKERS,
    apply_settings,
)


def _is_safe_redirect(target: str) -> bool:
    """Return True if *target* is a safe relative URL for post-login redirect.

    Rejects absolute URLs (``https://evil.com``), protocol-relative URLs
    (``//evil.com``), and anything that doesn't start with a single ``/``.
    This prevents open-redirect / phishing attacks via the ``next`` query
    parameter.
    """
    if not target:
        return False
    if not target.startswith('/'):
        return False
    if target.startswith('//'):
        return False
    parsed = urlparse(target)
    return parsed.scheme == '' and parsed.netloc == ''


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

        # Nickname and full_name are optional at signup — left as NULL
        # (display_name falls back to username) until the learner sets
        # them in Settings. We only strip/validate length here; the
        # settings_service validators are reused for consistency.
        from src.services.settings_service import validate_full_name, validate_nickname
        nickname = validate_nickname(request.form.get('nickname'))
        full_name = validate_full_name(request.form.get('full_name'))

        user = User(username=username, nickname=nickname, full_name=full_name,
                     email=email)
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
            if next_page and _is_safe_redirect(next_page):
                return redirect(next_page)
            return redirect(url_for('main.index'))

        flash('Invalid username or password.', 'error')
        return redirect(url_for('main.index'))

    # GET /login — the login form lives on the index page, so redirect there.
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


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User preferences — avatar, TTS narration toggle/speaker, lesson difficulty."""
    if request.method == 'POST':
        old_nick = current_user.nickname
        old_diff = current_user.lesson_difficulty
        old_speaker = current_user.tts_speaker
        _, message = apply_settings(
            current_user,
            avatar=request.form.get('avatar'),
            tts_enabled=request.form.get('tts_enabled', False),
            tts_speaker=request.form.get('tts_speaker'),
            lesson_difficulty=request.form.get('lesson_difficulty'),
            nickname=request.form.get('nickname'),
            full_name=request.form.get('full_name'),
        )
        db.session.commit()

        # Memory: record preference changes
        from src.services.mascot_memory import store_memory as _sm
        if current_user.nickname and current_user.nickname != old_nick:
            _sm(current_user.id, 'procedural',
                f"Likes to be called {current_user.nickname}")
        if current_user.lesson_difficulty != old_diff:
            _sm(current_user.id, 'semantic',
                f"Prefers {current_user.lesson_difficulty} difficulty")
        if current_user.tts_speaker != old_speaker:
            _sm(current_user.id, 'procedural',
                f"Prefers TTS voice {current_user.tts_speaker}")

        flash(message, 'success')
        return redirect(url_for('main.settings'))

    return render_template(
        'settings.html',
        avatars=ALLOWED_AVATARS,
        speakers=TTS_SPEAKERS,
        difficulty_index=DIFFICULTY_LEVELS.index(current_user.lesson_difficulty)
        if current_user.lesson_difficulty in DIFFICULTY_LEVELS
        else DIFFICULTY_LEVELS.index(DEFAULT_DIFFICULTY),
    )


@bp.route('/settings/forget-memories', methods=['POST'])
@login_required
def forget_memories():
    """Delete all mascot memories for the learner (privacy control)."""
    from src.services.mascot_memory import delete_all as _forget
    count = _forget(current_user.id)
    if count:
        flash(f'Forgot {count} memorized detail(s) about you. Starting fresh!', 'success')
    else:
        flash('The mascot had nothing memorized about you.', 'info')
    return redirect(url_for('main.settings'))
