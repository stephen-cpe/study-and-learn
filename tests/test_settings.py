"""
Tests for the user Settings page and persistence of user preferences.

Covers:
  - User model defaults (avatar, tts_enabled, tts_speaker, lesson_difficulty)
  - settings_service validators (reject junk, fall back to defaults)
  - /settings GET/POST route (login required, form persistence)
  - Navbar avatar in base.html renders the user's avatar, not avatar-0.png
  - Avatar assets exist on disk in the new images/avatars/ subdirectory
"""
import pytest
import tempfile
from cachelib import FileSystemCache
from pathlib import Path

from src import create_app, db
from src.models import User
from src.services.settings_service import (
    ALLOWED_AVATARS,
    DEFAULT_AVATAR,
    DEFAULT_DIFFICULTY,
    DEFAULT_TTS_SPEAKER,
    DIFFICULTY_LEVELS,
    TTS_SPEAKERS,
    apply_settings,
    validate_avatar,
    validate_difficulty,
    validate_tts_speaker,
)


# ── Shared app fixture (mirrors existing test patterns) ────────────────────


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        app_instance = create_app()
        app_instance.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(
                cache_dir=temp_dir, threshold=500, mode=0o700
            ),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app_instance)
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app_instance.extensions.pop('sqlalchemy', None)
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            yield app_instance
            db.session.remove()
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    def _make(username='tester', password='testpass1', **kwargs):
        with app.app_context():
            user = User(username=username, email=f'{username}@example.com', **kwargs)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            return user.id
    return _make


def _login(client, username='tester', password='testpass1'):
    return client.post(
        '/login',
        data={'username': username, 'password': password},
        follow_redirects=False,
    )


# ── Validator unit tests ───────────────────────────────────────────────────


class TestSettingsServiceValidators:
    def test_known_avatar_is_kept(self):
        assert validate_avatar('avatar-3.png') == 'avatar-3.png'

    def test_unknown_avatar_falls_back_to_default(self):
        assert validate_avatar('not-an-avatar.png') == DEFAULT_AVATAR
        assert validate_avatar('') == DEFAULT_AVATAR
        assert validate_avatar(None) == DEFAULT_AVATAR

    def test_known_speaker_kept(self):
        assert validate_tts_speaker('Emma') == 'Emma'

    def test_unknown_speaker_falls_back_to_default(self):
        assert validate_tts_speaker('Zelda') == DEFAULT_TTS_SPEAKER
        assert validate_tts_speaker('') == DEFAULT_TTS_SPEAKER

    def test_known_difficulty_kept(self):
        assert validate_difficulty('Easy') == 'Easy'
        assert validate_difficulty('Hard') == 'Hard'

    def test_unknown_difficulty_falls_back_to_default(self):
        assert validate_difficulty('Insane') == DEFAULT_DIFFICULTY
        assert validate_difficulty('') == DEFAULT_DIFFICULTY

    def test_allowed_lists_have_expected_size(self):
        assert len(ALLOWED_AVATARS) == 9
        assert TTS_SPEAKERS == ['Ava', 'Emma', 'Ryan', 'Andrew']
        assert DIFFICULTY_LEVELS == ['Easy', 'Normal', 'Hard']

    def test_apply_settings_updates_only_changed_fields(self, app, make_user):
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            changed, msg = apply_settings(user, avatar='avatar-5.png')
            assert changed is True
            assert user.avatar == 'avatar-5.png'
            assert user.tts_enabled is False
            assert user.tts_speaker == 'Ava'
            assert 'Avatar' in msg

    def test_apply_settings_ignores_unchanged_values(self, app, make_user):
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            changed, _ = apply_settings(user, tts_speaker='Ava')
            assert changed is False

    def test_apply_settings_rejects_garbage_via_fallback(self, app, make_user):
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            apply_settings(user, avatar='hax0r.png', tts_speaker='DropTable', lesson_difficulty='YOLO')
            assert user.avatar == DEFAULT_AVATAR
            assert user.tts_speaker == DEFAULT_TTS_SPEAKER
            assert user.lesson_difficulty == DEFAULT_DIFFICULTY


# ── User model defaults ────────────────────────────────────────────────────


class TestUserModelDefaults:
    def test_new_user_has_expected_settings_defaults(self, app, make_user):
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            assert user.avatar == 'avatar-0.png'
            assert user.tts_enabled is False
            assert user.tts_speaker == 'Ava'
            assert user.lesson_difficulty == 'Normal'


# ── /settings route ────────────────────────────────────────────────────────


class TestSettingsRoute:
    def test_anonymous_user_is_redirected_to_login(self, client):
        resp = client.get('/settings')
        assert resp.status_code in (302, 303)
        assert '/login' in resp.headers.get('Location', '')

    def test_get_renders_settings_page(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.get('/settings')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'Settings' in body
        assert 'avatar-0.png' in body
        # The avatar URL must point to the new avatars/ subdirectory
        assert 'images/avatars/avatar-0.png' in body
        assert 'Text to Speech' in body
        assert 'Lesson Difficulty' in body
        # The settings.js file must actually be loaded — otherwise the
        # avatar modal never opens when the user clicks their profile pic.
        assert 'js/settings.js' in body
        # All 9 avatar cells should be rendered in the modal markup
        for av in ALLOWED_AVATARS:
            assert f'images/avatars/{av}' in body

    def test_post_persists_avatar(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.post(
            '/settings',
            data={
                'avatar': 'avatar-4.png',
                'tts_enabled': '',
                'tts_speaker': 'Ava',
                'lesson_difficulty': 'Normal',
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            user = User.query.filter_by(username='tester').first()
            assert user.avatar == 'avatar-4.png'

    def test_post_persists_tts_and_difficulty(self, app, client, make_user):
        make_user()
        _login(client)
        resp = client.post(
            '/settings',
            data={
                'avatar': 'avatar-0.png',
                'tts_enabled': 'on',
                'tts_speaker': 'Ryan',
                'lesson_difficulty': 'Hard',
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            user = User.query.filter_by(username='tester').first()
            assert user.tts_enabled is True
            assert user.tts_speaker == 'Ryan'
            assert user.lesson_difficulty == 'Hard'

    def test_post_rejects_garbage_values(self, app, client, make_user):
        make_user()
        _login(client)
        client.post(
            '/settings',
            data={
                'avatar': 'malicious.png',
                'tts_enabled': 'on',
                'tts_speaker': 'Voldemort',
                'lesson_difficulty': 'YOLO',
            },
            follow_redirects=False,
        )
        with app.app_context():
            user = User.query.filter_by(username='tester').first()
            assert user.avatar == 'avatar-0.png'
            assert user.tts_speaker == 'Ava'
            assert user.lesson_difficulty == 'Normal'
            assert user.tts_enabled is True  # bool field untouched

    def test_post_unchecked_checkbox_disables_tts(self, app, client, make_user):
        """Regression: an unchecked checkbox is absent from the POST body.
        The route must interpret that absence as False so a user who enabled
        TTS can later disable it. Previously `request.form.get('tts_enabled')`
        returned None and apply_settings skipped the field entirely."""
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            user.tts_enabled = True
            db.session.commit()
        _login(client)
        # NOTE: 'tts_enabled' intentionally omitted from the form data,
        # mirroring how a real browser submits an unchecked checkbox.
        resp = client.post(
            '/settings',
            data={
                'avatar': 'avatar-0.png',
                'tts_speaker': 'Ava',
                'lesson_difficulty': 'Normal',
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        with app.app_context():
            user = db.session.get(User, uid)
            assert user.tts_enabled is False

    def test_get_reflects_existing_preferences(self, app, client, make_user):
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            user.avatar = 'avatar-7.png'
            user.tts_enabled = True
            user.tts_speaker = 'Andrew'
            user.lesson_difficulty = 'Easy'
            db.session.commit()
        _login(client)
        body = client.get('/settings').get_data(as_text=True)
        assert 'avatar-7.png' in body
        assert 'value="Andrew" selected' in body
        # The Easy tick is the leftmost (index 0) on the slider
        assert 'value="0"' in body

    def test_logout_link_still_present(self, app, client, make_user):
        make_user()
        _login(client)
        body = client.get('/').get_data(as_text=True)
        assert 'Logout' in body
        assert 'Settings' in body
        assert 'Reset Password' in body


# ── Navbar avatar wiring ──────────────────────────────────────────────────


class TestNavbarAvatar:
    def test_navbar_avatar_reflects_user_choice(self, app, client, make_user):
        uid = make_user()
        with app.app_context():
            user = db.session.get(User, uid)
            user.avatar = 'avatar-2.png'
            db.session.commit()
        _login(client)
        body = client.get('/').get_data(as_text=True)
        # The navbar should show the chosen avatar, not the hard-coded default
        assert 'images/avatars/avatar-2.png' in body

    def test_default_new_user_keeps_avatar_zero(self, app, client, make_user):
        make_user()
        _login(client)
        body = client.get('/').get_data(as_text=True)
        assert 'images/avatars/avatar-0.png' in body

    def test_navbar_uses_avatars_subdirectory(self, app, client, make_user):
        """After the images/ reorganization, the navbar must read from
        images/avatars/, not images/<bare-filename>."""
        make_user()
        _login(client)
        body = client.get('/').get_data(as_text=True)
        # Positive: the new path is present
        assert 'images/avatars/avatar-0.png' in body
        # Negative: the old flat path is gone
        assert "filename='images/avatar-0.png'" not in body
        assert '"images/avatar-0.png"' not in body


# ── Static asset layout (regression guard for images/ reorganization) ──────


class TestStaticAssetLayout:
    """Asserts that the on-disk layout under src/static/images/ matches
    the structure expected by the templates. If anyone moves files back
    into a flat directory, these tests will fail."""

    AVATAR_DIR = Path(__file__).resolve().parent.parent / 'src' / 'static' / 'images' / 'avatars'
    MASCOTS_DIR = Path(__file__).resolve().parent.parent / 'src' / 'static' / 'images' / 'mascots'

    def test_avatar_directory_exists(self):
        assert self.AVATAR_DIR.is_dir(), f'Missing {self.AVATAR_DIR}'

    def test_all_avatar_files_present(self):
        for i in range(9):
            assert (self.AVATAR_DIR / f'avatar-{i}.png').is_file(), (
                f'Missing avatar-{i}.png in {self.AVATAR_DIR}'
            )

    def test_mascots_directory_has_state_subdirs(self):
        for state in ('idle', 'busy', 'happy', 'error'):
            assert (self.MASCOTS_DIR / state).is_dir(), (
                f'Missing {self.MASCOTS_DIR / state}'
            )

    def test_mascot_base_assets_at_state_subdir_root(self):
        assert (self.MASCOTS_DIR / 'mascot-robot.png').is_file()
        assert (self.MASCOTS_DIR / 'mascot-robot-static.png').is_file()

    def test_each_state_has_gif_and_sprite(self):
        for state in ('idle', 'busy', 'happy', 'error'):
            gif = self.MASCOTS_DIR / state / f'mascot-{state}.gif'
            sprite = self.MASCOTS_DIR / state / f'mascot-{state}-sprite.png'
            assert gif.is_file(), f'Missing {gif}'
            assert sprite.is_file(), f'Missing {sprite}'
