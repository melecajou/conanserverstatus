import sqlite3
import pytest
from datetime import datetime, timedelta
import os

from utils.database import initialize_global_db, update_vip_expiry, get_global_vip, set_global_vip

@pytest.fixture
def global_db():
    db_path = "test_global_registry.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    initialize_global_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)

def test_update_vip_expiry_existing_user(global_db):
    discord_id = 123456
    set_global_vip(discord_id, 1, "2024-01-01T00:00:00", global_db)

    result = update_vip_expiry(discord_id, 30, global_db)
    assert result is True

    vip_data = get_global_vip(discord_id, global_db)
    assert vip_data is not None
    assert vip_data["vip_level"] == 1

    expiry_date = datetime.fromisoformat(vip_data["vip_expiry"])
    expected_expiry = datetime.now() + timedelta(days=30)

    assert abs((expiry_date - expected_expiry).total_seconds()) < 5

def test_update_vip_expiry_non_existing_user(global_db):
    discord_id = 654321

    result = update_vip_expiry(discord_id, 30, global_db)
    assert result is False

    vip_data = get_global_vip(discord_id, global_db)
    assert vip_data is None
