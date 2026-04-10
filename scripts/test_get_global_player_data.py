import sys
import os
import time
import sqlite3

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.database import get_global_player_data, initialize_global_db, link_discord_to_platform, set_global_vip, _GLOBAL_PLAYER_CACHE

def test_get_global_player_data():
    db_path = "data/test_functional_db.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    initialize_global_db(db_path)

    # 1. Test fetching non-existent data
    _GLOBAL_PLAYER_CACHE.clear()
    pids = ["pid1", "pid2"]
    data = get_global_player_data(pids, global_db_path=db_path)

    assert data["pid1"]["discord_id"] is None
    assert data["pid1"]["vip_level"] == 0

    # Check cache
    assert ("pid1", db_path) in _GLOBAL_PLAYER_CACHE
    assert _GLOBAL_PLAYER_CACHE[("pid1", db_path)]["data"]["discord_id"] is None

    # 2. Test fetching existent data
    link_discord_to_platform("pid3", 12345, global_db_path=db_path)
    set_global_vip(12345, 2, "2099-01-01", global_db_path=db_path)

    # Cache should have been invalidated by link/set_global_vip
    data = get_global_player_data(["pid3"], global_db_path=db_path)
    assert data["pid3"]["discord_id"] == 12345
    assert data["pid3"]["vip_level"] == 2

    # 3. Test that cache is actually used
    _GLOBAL_PLAYER_CACHE[("pid3", db_path)]["data"]["vip_level"] = 99
    data = get_global_player_data(["pid3"], global_db_path=db_path)
    assert data["pid3"]["vip_level"] == 99, "Should have used cached value"

    # 4. Test multiple IDs mixed
    data = get_global_player_data(["pid1", "pid3", "pid4"], global_db_path=db_path)
    assert data["pid1"]["discord_id"] is None
    assert data["pid3"]["vip_level"] == 99
    assert data["pid4"]["discord_id"] is None

    print("Functional tests for get_global_player_data passed!")

    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    try:
        test_get_global_player_data()
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
