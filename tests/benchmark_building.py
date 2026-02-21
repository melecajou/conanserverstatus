import sqlite3
import time
import os
import sys
import unittest.mock
from contextlib import contextmanager
from types import ModuleType

# Add project root to path so we can import cogs
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock config module
mock_config = ModuleType("config")
mock_config.SERVERS = []
sys.modules["config"] = mock_config

from cogs.building import get_owner_details, get_batch_owner_details

DB_PATH = "tests/benchmark_game.db"
PLAYER_DB_PATH = "tests/benchmark_player.db"

def setup_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Create tables
    cur.execute("CREATE TABLE guilds (guildId INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT, playerId INTEGER, guild INTEGER)")
    cur.execute("CREATE TABLE account (id INTEGER PRIMARY KEY, platformId TEXT)")

    # Populate with data
    # 500 guilds, each with 5 members
    owners = []

    # Guilds
    for i in range(1, 501):
        guild_id = i
        cur.execute("INSERT INTO guilds (guildId, name) VALUES (?, ?)", (guild_id, f"Guild_{guild_id}"))
        owners.append((guild_id, 100)) # owner_id, pieces

        # Members
        for j in range(5):
            char_id = i * 1000 + j
            player_id = char_id # simplify
            platform_id = f"PID_{player_id}"

            cur.execute("INSERT INTO characters (id, char_name, playerId, guild) VALUES (?, ?, ?, ?)",
                        (char_id, f"Char_{char_id}", player_id, guild_id))
            cur.execute("INSERT INTO account (id, platformId) VALUES (?, ?)", (player_id, platform_id))

    # Solo Players (another 500)
    for i in range(501, 1001):
        char_id = i * 1000
        player_id = char_id
        platform_id = f"PID_{player_id}"

        cur.execute("INSERT INTO characters (id, char_name, playerId, guild) VALUES (?, ?, ?, NULL)",
                    (char_id, f"SoloChar_{char_id}", player_id))
        cur.execute("INSERT INTO account (id, platformId) VALUES (?, ?)", (player_id, platform_id))
        owners.append((char_id, 50))

    con.commit()
    con.close()
    return owners

def mock_get_global_player_data(platform_ids, global_db_path=None):
    # Simulate a fast lookup
    return {pid: {"vip_level": 1 if int(pid.split('_')[1]) % 10 == 0 else 0} for pid in platform_ids}

def run_benchmark():
    owners_list = setup_db()
    print(f"Setup complete. Testing with {len(owners_list)} owners.")

    owner_ids = [x[0] for x in owners_list]

    # Mocking get_global_player_data in cogs.building scope
    with unittest.mock.patch('cogs.building.get_global_player_data', side_effect=mock_get_global_player_data):

        # Test 1: Loop (Simulating old behavior, though using the wrapper)
        print("Benchmarking Loop (Wrapper)...")
        start_time = time.time()
        for owner_id in owner_ids:
            get_owner_details(owner_id, DB_PATH, PLAYER_DB_PATH)
        end_time = time.time()
        print(f"Loop Time: {end_time - start_time:.4f} seconds")

        # Test 2: Batch
        print("Benchmarking Batch...")
        start_time = time.time()
        get_batch_owner_details(owner_ids, DB_PATH, PLAYER_DB_PATH)
        end_time = time.time()
        print(f"Batch Time: {end_time - start_time:.4f} seconds")

    # Clean up
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

if __name__ == "__main__":
    run_benchmark()
