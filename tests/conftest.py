import pytest


def pytest_configure(config):
    """Add warning filters before test collection."""
    config.addinivalue_line(
        "filterwarnings",
        "ignore::DeprecationWarning:flask_login.login_manager",
    )


@pytest.fixture(autouse=True)
def isolate_figure_store(tmp_path, monkeypatch):
    """Keep test-generated figure thumbnails out of the real data/figures."""
    import src.services.figure_store as figure_store

    monkeypatch.setattr(figure_store, "FIGURES_DIR", str(tmp_path / "figures"))
