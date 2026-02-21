import asyncio
import sqlite3
import os
import sys
import time
import unittest.mock
from types import ModuleType

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock config module
mock_config = ModuleType("config")
mock_config.SERVERS = []
sys.modules["config"] = mock_config

from cogs.building import get_batch_owner_details

DB_PATH = "scripts/reproduce_building_game.db"
PLAYER_DB_PATH = "scripts/reproduce_building_player.db"

def setup_db(count=5000):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("CREATE TABLE guilds (guildId INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT, playerId INTEGER, guild INTEGER)")
    cur.execute("CREATE TABLE account (id INTEGER PRIMARY KEY, platformId TEXT)")

    owner_ids = []

    # Create a lot of data to ensure the query takes time
    print(f"Generating {count} records...")

    # Guilds
    # We will query chunk by chunk (900), so let's make sure we have multiple chunks
    for i in range(1, count + 1):
        guild_id = i
        cur.execute("INSERT INTO guilds (guildId, name) VALUES (?, ?)", (guild_id, f"Guild_{guild_id}"))
        owner_ids.append(guild_id)

        # Add some members to make queries more complex
        for j in range(2):
            char_id = i * 100 + j
            player_id = char_id
            platform_id = f"PID_{player_id}"
            cur.execute("INSERT INTO characters (id, char_name, playerId, guild) VALUES (?, ?, ?, ?)",
                        (char_id, f"Char_{char_id}", player_id, guild_id))
            cur.execute("INSERT INTO account (id, platformId) VALUES (?, ?)", (player_id, platform_id))

    con.commit()
    con.close()
    return owner_ids

def mock_get_global_player_data(platform_ids, global_db_path=None):
    # Simulate a fast lookup
    return {pid: {"vip_level": 0} for pid in platform_ids}

async def heartbeat(monitor_duration):
    """Monitors the event loop lag."""
    print("Heartbeat started")
    start_time = time.time()
    max_lag = 0
    last_beat = start_time

    while time.time() - start_time < monitor_duration:
        await asyncio.sleep(0.01) # Sleep for 10ms
        now = time.time()
        # Expected duration is 0.01s. Lag is anything above that.
        lag = (now - last_beat) - 0.01
        if lag > max_lag:
            max_lag = lag
        last_beat = now

    print(f"Heartbeat finished. Max lag: {max_lag*1000:.2f}ms")
    return max_lag

async def main():
    owner_ids = setup_db(count=5000)

    print("\n--- BASELINE: Synchronous Execution ---")

    monitor_task = asyncio.create_task(heartbeat(2.0))
    await asyncio.sleep(0.1)

    # Run the blocking operation
    with unittest.mock.patch('cogs.building.get_global_player_data', side_effect=mock_get_global_player_data):
        start = time.time()
        get_batch_owner_details(owner_ids, DB_PATH, PLAYER_DB_PATH)
        duration = time.time() - start

    print(f"Sync operation took {duration:.4f}s")

    max_lag = await monitor_task

    print(f"Baseline Max Loop Lag: {max_lag*1000:.2f}ms")


    print("\n--- VERIFICATION: asyncio.to_thread ---")

    monitor_task = asyncio.create_task(heartbeat(2.0))
    await asyncio.sleep(0.1)

    with unittest.mock.patch('cogs.building.get_global_player_data', side_effect=mock_get_global_player_data):
        start = time.time()
        # This is what we will implement in the code
        await asyncio.to_thread(get_batch_owner_details, owner_ids, DB_PATH, PLAYER_DB_PATH)
        duration = time.time() - start

    print(f"Threaded operation took {duration:.4f}s")
    max_lag_threaded = await monitor_task
    print(f"Threaded Max Loop Lag: {max_lag_threaded*1000:.2f}ms")

    # Cleanup
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

if __name__ == "__main__":
    asyncio.run(main())
