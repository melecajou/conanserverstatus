import os
import pytest
import shutil

def pytest_sessionstart(session):
    """
    Called after the Session object has been created and
    before performing collection and entering the run test loop.
    Creates a dummy config.py to allow tests to run, backing up existing one.
    """
    config_path = "config.py"
    backup_path = "config.py.test_bak"
    
    if os.path.exists(config_path):
        shutil.move(config_path, backup_path)

    config_content = """
STATUS_BOT_TOKEN = "test_token"
CLUSTER_STATUS = {"ENABLED": False, "CHANNEL_ID": 0}
SERVERS = []
LANGUAGE = "en"
    """
    with open(config_path, "w") as f:
        f.write(config_content)

def pytest_sessionfinish(session, exitstatus):
    """
    Called after the whole test run finishes.
    Removes the dummy config.py and restores backup.
    """
    config_path = "config.py"
    backup_path = "config.py.test_bak"
    
    if os.path.exists(config_path):
        os.remove(config_path)
        
    if os.path.exists(backup_path):
        shutil.move(backup_path, config_path)
