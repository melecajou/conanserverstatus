import os
import pytest

def pytest_sessionstart(session):
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    Creates a dummy config.py to allow tests to run.
    """
    config_content = """
STATUS_BOT_TOKEN = "test_token"
SERVERS = []
LANGUAGE = "en"
    """
    config_path = "config.py"
    with open(config_path, "w") as f:
        f.write(config_content)

def pytest_sessionfinish(session, exitstatus):
    """
    Called after the whole test run finishes.
    Removes the dummy config.py.
    """
    config_path = "config.py"
    if os.path.exists(config_path):
        os.remove(config_path)
