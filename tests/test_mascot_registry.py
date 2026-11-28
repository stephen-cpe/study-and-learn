"""Tests for the mascot registry and the rendered mascot config.

The registry (src/services/mascot_registry.py) owns the mascot ids, the
cached manifests and the behaviour parameters from docs/MASCOTS.md
sections 5-7; _mascot.html renders them as inline JSON for the sprite
player. These tests pin those parameters to the spec.
"""
import json
import re
import tempfile

import pytest
from cachelib import FileSystemCache

from src import create_app, db
from src.models import User
from src.services import mascot_registry


def test_default_mascot_is_raster():
    assert mascot_registry.DEFAULT_MASCOT == 'raster'
    assert mascot_registry.MASCOT_IDS == ('raster', 'pip', 'trace')
    assert mascot_registry.active_mascot_id() == 'raster'


def test_active_mascot_fails_safe_when_the_lookup_raises(client, monkeypatch):
    """The context processor runs on every page, including error pages; a
    database failure while reading the learner's choice must not break them."""
    import flask_login

    class BrokenUser:
        is_authenticated = True

        @property
        def mascot(self):
            raise RuntimeError('database is down')

    monkeypatch.setattr(flask_login, 'current_user', BrokenUser())
    with client.application.test_request_context('/'):
        assert mascot_registry.active_mascot_id() == 'raster'


def test_picker_options_match_the_display_registry():
    options = mascot_registry.picker_options()
    assert [option['id'] for option in options] == ['raster', 'pip', 'trace']
    for option in options:
        display = mascot_registry.DISPLAY[option['id']]
        assert option['name'] == display['name']
        assert option['tagline'] == display['tagline']
        assert option['hello_ms'] == mascot_registry.load_manifest(
            option['id'])['animations']['hello']['total_ms']


def test_unknown_mascot_id_falls_back_to_default():
    assert mascot_registry.get_mascot('nope')['id'] == 'raster'
    assert mascot_registry.get_mascot(None)['id'] == 'raster'
    assert mascot_registry.build_mascot_config('nope')['id'] == 'raster'


def test_display_names_and_taglines():
    for mid, name, tagline in (
        ('raster', 'Raster', 'Talkative co-pilot. Explains everything.'),
        ('pip', 'Pip', 'Tiny T. rex. Huge feelings.'),
        ('trace', 'Trace', 'Quiet paperclip. Notices everything.'),
    ):
        mascot = mascot_registry.get_mascot(mid)
        assert mascot['name'] == name
        assert mascot['tagline'] == tagline


def test_all_three_manifests_load():
    for mid in ('raster', 'pip', 'trace'):
        mascot = mascot_registry.get_mascot(mid)
        assert mascot['id'] == mid
        manifest = mascot['manifest']
        assert manifest['frame_width'] > 0
        assert manifest['frame_height'] > 0
        assert len(manifest['animations']) == 32


def test_config_shape_matches_manifest():
    cfg = mascot_registry.build_mascot_config()
    assert cfg['id'] == 'raster'
    assert cfg['asset_base'].endswith('/images/mascots/raster/')
    assert cfg['still'] == 'still.png'
    assert (cfg['frame_width'], cfg['frame_height']) == (90, 96)
    assert isinstance(cfg['ground_offset'], int) and cfg['ground_offset'] >= 0
    assert len(cfg['animations']) == 32
    for anim in cfg['animations'].values():
        assert anim['sheet'].endswith('.png')
        assert anim['frames'] and all(d > 0 for d in anim['frames'])
        assert isinstance(anim['loop'], bool)


def test_behaviour_params_match_mascots_doc():
    """Sleep timings, chatter and click ratios (docs/MASCOTS.md §5-§7)."""
    beh = {mid: mascot_registry.build_mascot_config(mid)['behaviour']
           for mid in ('raster', 'pip', 'trace')}
    # Sleep: sleepy / power-down after N and M minutes (section 6).
    assert beh['raster']['sleepy_after_ms'] == 5 * 60 * 1000
    assert beh['raster']['power_down_after_ms'] == 15 * 60 * 1000
    assert beh['pip']['sleepy_after_ms'] == 3 * 60 * 1000
    assert beh['pip']['power_down_after_ms'] == 10 * 60 * 1000
    assert beh['trace']['sleepy_after_ms'] == 5 * 60 * 1000
    assert beh['trace']['power_down_after_ms'] == 15 * 60 * 1000
    # Chatter: at least 180 s after the last line, Raster only (section 5).
    for mid in ('raster', 'pip', 'trace'):
        assert beh[mid]['chatter_gap_ms'] == 180000
    assert beh['raster']['chatter_enabled'] is True
    assert beh['pip']['chatter_enabled'] is False
    assert beh['trace']['chatter_enabled'] is False
    # Click shuffle bag sizes: 1 talk in 4 / 6 / 6 (section 5).
    assert beh['raster']['click_talk_every'] == 4
    assert beh['pip']['click_talk_every'] == 6
    assert beh['trace']['click_talk_every'] == 6
    # Trace "writes" where Raster and Pip "speak" (sections 2 and 6).
    assert beh['raster']['talk_anim'] == 'speaking'
    assert beh['pip']['talk_anim'] == 'speaking'
    assert beh['trace']['talk_anim'] == 'writing'
    # Hover fires at 500 ms (section 6).
    for mid in ('raster', 'pip', 'trace'):
        assert beh[mid]['hover_delay_ms'] == 500


def test_idle_pools_and_gaps_match_mascots_doc():
    """Weighted idle pools and gap ranges (docs/MASCOTS.md section 6)."""
    expected = {
        'raster': ([10000, 20000], {
            'idle-double-blink': 3, 'idle-look-around': 3,
            'idle-antenna-settle': 3, 'cursor-glance': 2, 'curious': 1,
            'look-up': 1, 'look-left': 1, 'look-right': 1, 'look-down': 1,
        }),
        'pip': ([5000, 10000], {
            'idle-tail-sway': 4, 'idle-look-around': 3,
            'idle-double-blink': 2, 'curious': 2, 'cursor-glance': 2,
            'notice': 1, 'look-up': 1, 'look-left': 1, 'look-right': 1,
            'look-down': 1,
        }),
        'trace': ([20000, 40000], {
            'cursor-glance': 3, 'idle-look-around': 3, 'idle-sway': 3,
            'idle-double-blink': 2, 'curious': 2, 'look-up': 1,
            'look-left': 1, 'look-right': 1, 'look-down': 1,
        }),
    }
    for mid, (gap, pool) in expected.items():
        beh = mascot_registry.build_mascot_config(mid)['behaviour']
        assert beh['idle_gap_ms'] == gap, f'{mid}: idle gap'
        got = {entry['anim']: entry['weight'] for entry in beh['idle_pool']}
        assert got == pool, f'{mid}: idle pool'


def test_click_reaction_pools_match_mascots_doc():
    """Click reaction pools (docs/MASCOTS.md section 7)."""
    expected = {
        'raster': ['acknowledge', 'curious', 'idle-antenna-settle', 'look-up'],
        'pip': ['celebrate', 'curious', 'idle-tail-sway', 'acknowledge'],
        'trace': ['curious', 'unsure', 'acknowledge', 'notice'],
    }
    for mid, pool in expected.items():
        beh = mascot_registry.build_mascot_config(mid)['behaviour']
        assert beh['click_reactions'] == pool, f'{mid}: click reactions'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('AI_MOCK', 'true')
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
            user = User(username='regtester', email='reg@example.com',
                        can_generate_lessons=True)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'regtester',
                                       'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


def test_rendered_page_contains_mascot_config(client):
    """A page with _mascot.html must carry the config JSON: Raster and
    all 32 of his animations."""
    body = client.get('/').data.decode('utf-8')
    m = re.search(
        r'<script type="application/json" id="mascot-config">(.*?)</script>',
        body, re.S,
    )
    assert m, 'index.html must render the mascot config JSON block'
    cfg = json.loads(m.group(1))
    assert cfg['id'] == 'raster'
    assert len(cfg['animations']) == 32
    assert cfg['animations'] == mascot_registry.load_manifest('raster')[
        'animations']
    assert cfg['behaviour']['chatter_gap_ms'] == 180000
