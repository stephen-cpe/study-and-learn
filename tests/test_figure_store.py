"""
Tests for source-figure persistence (slice 4): figure_store save/get/attach
plus the auth-scoped /figures/<hash>/<file> serving route.
"""
import json
import tempfile

import pytest
from cachelib import FileSystemCache
from PIL import Image

from src import create_app, db
from src.models import StudyPath, User


@pytest.fixture
def fig_app(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    monkeypatch.setenv('CI', 'true')
    monkeypatch.setenv('AI_MOCK', 'true')
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(cache_dir=temp_dir, threshold=500, mode=0o700),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.extensions.pop('sqlalchemy', None)
        db.init_app(app)
        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()


def _make_image(path, size=(400, 300)):
    Image.new("RGB", size, color="white").save(path, "PNG")
    return path


def test_save_and_get_roundtrip(tmp_path, monkeypatch):
    import src.services.figure_store as fs
    monkeypatch.setattr(fs, "FIGURES_DIR", str(tmp_path))
    src_img = _make_image(str(tmp_path / "page_1.png"), (2000, 1500))
    name = fs.save_figure("a" * 64, src_img, caption="A circuit", label="doc — page 1")
    assert name and name.endswith(".png")
    figs = fs.get_figures("a" * 64)
    assert len(figs) == 1
    assert figs[0]["caption"] == "A circuit"
    # Downscaled to max 1024.
    saved = Image.open(str(tmp_path / ("a" * 64) / name))
    assert max(saved.size) <= 1024


def test_save_figure_never_raises(tmp_path, monkeypatch):
    import src.services.figure_store as fs
    monkeypatch.setattr(fs, "FIGURES_DIR", str(tmp_path))
    assert fs.save_figure("", "/nonexistent.png") is None
    assert fs.get_figures("") == []
    assert fs.get_figures("b" * 64) == []


def test_get_figures_rejects_traversal(tmp_path, monkeypatch):
    import src.services.figure_store as fs
    monkeypatch.setattr(fs, "FIGURES_DIR", str(tmp_path))
    target = tmp_path / ("c" * 64)
    target.mkdir()
    (target / "manifest.json").write_text(json.dumps({
        "file_hash": "c" * 64,
        "figures": [{"file": "../evil.png", "caption": "x", "label": ""}],
    }))
    assert fs.get_figures("c" * 64) == []


def test_attach_figures_adds_urls(tmp_path, monkeypatch):
    import src.services.figure_store as fs
    monkeypatch.setattr(fs, "FIGURES_DIR", str(tmp_path))
    src_img = _make_image(str(tmp_path / "fig.png"))
    fs.save_figure("d" * 64, src_img, caption="Cap", label="L")
    sources = [{"source_hash": "d" * 64, "text": "t"},
               {"source_hash": "e" * 64, "text": "t2"}]
    out = fs.attach_figures(sources)
    assert len(out[0]["figures"]) == 1
    assert out[0]["figures"][0]["url"].startswith("/figures/" + "d" * 64)
    assert "figures" not in out[1]


def _login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=False)


def test_figures_route_authz(fig_app, tmp_path, monkeypatch):
    import src.services.figure_store as fs
    monkeypatch.setattr(fs, "FIGURES_DIR", str(tmp_path))
    file_hash = "f" * 64
    src_img = _make_image(str(tmp_path / "p.png"))
    name = fs.save_figure(file_hash, src_img, caption="Cap", label="L")

    with fig_app.app_context():
        owner = User(username='owner', email='o@example.com', can_generate_lessons=True)
        owner.set_password('pass')
        intruder = User(username='intruder', email='i@example.com', can_generate_lessons=True)
        intruder.set_password('pass')
        db.session.add_all([owner, intruder])
        db.session.commit()
        path = StudyPath(user_id=owner.id, title='T', learning_goal='G',
                         status='active', content_data='[]',
                         file_hashes=json.dumps([file_hash]))
        db.session.add(path)
        db.session.commit()

    client = fig_app.test_client()
    _login(client, 'intruder', 'pass')
    assert client.get(f'/figures/{file_hash}/{name}').status_code == 404
    client.get('/logout', follow_redirects=False)

    _login(client, 'owner', 'pass')
    resp = client.get(f'/figures/{file_hash}/{name}')
    assert resp.status_code == 200
    assert resp.content_type == 'image/png'
    assert client.get(f'/figures/{file_hash}/missing.png').status_code == 404
    assert client.get(f'/figures/{file_hash}/..%2Fevil.png').status_code == 404
