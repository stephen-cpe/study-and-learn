def pytest_configure(config):
    """Add warning filters before test collection."""
    config.addinivalue_line(
        "filterwarnings",
        "ignore::DeprecationWarning:flask_login.login_manager",
    )
