import asyncio
import sqlite3
import os
import time
import json
import logging
import sys
import shutil
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# Define temporary paths
TEMP_DIR = os.path.join(PROJECT_ROOT, "temp_killfeed_bench")
GAME_DB_PATH = os.path.join(TEMP_DIR, "game.db")
SPAWNS_DB_PATH = os.path.join(TEMP_DIR, "spawns.db")
LAST_EVENT_FILE = os.path.join(TEMP_DIR, "last_event.txt")
RANKING_DB_PATH = os.path.join(TEMP_DIR, "ranking.db")
STATE_FILE = os.path.join(TEMP_DIR, "ranking_state.json")

# Create a dummy config module
class MockConfig:
    KILLFEED_SPAWNS_DB = SPAWNS_DB_PATH
    KILLFEED_RANKING_DB = RANKING_DB_PATH
    KILLFEED_STATE_FILE = STATE_FILE
    SERVERS = [
        {
            "NAME": "Test Server",
            "DB_PATH": GAME_DB_PATH,
            "KILLFEED_CONFIG": {
                "ENABLED": True,
                "CHANNEL_ID": 123,
                "RANKING_CHANNEL_ID": 456,
                "LAST_EVENT_FILE": LAST_EVENT_FILE,
                "PVP_ONLY": False
            }
        }
    ]
    KILLFEED_UNIFIED_RANKINGS = []

# Inject mock config
sys.modules["config"] = MockConfig
import config

# Now import the cog
from cogs.killfeed import KillfeedCog

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_databases():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    # Initialize Last Event File
    with open(LAST_EVENT_FILE, "w") as f:
        f.write("0")

    # Create Game DB
    print(f"Creating Game DB at {GAME_DB_PATH}")
    con = sqlite3.connect(GAME_DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE game_events (
            worldTime REAL,
            eventType INTEGER,
            causerName TEXT,
            ownerName TEXT,
            argsMap TEXT
        )
    """)

    # Insert many events
    print("Generating 10,000 events...")
    events = []
    # Make sure we have events after timestamp 0
    start_time = 100
    for i in range(10000):
        world_time = start_time + i
        event_type = 103 # DEATH_EVENT_TYPE
        causer_name = f"Killer_{i % 100}"
        owner_name = f"Owner_{i % 100}"

        # argsMap JSON
        npc_id = f"NPC_{i % 50}" if i % 2 == 0 else None
        args_map = json.dumps({
            "nonPersistentCauser": npc_id
        })

        events.append((world_time, event_type, causer_name, owner_name, args_map))

    cur.executemany("INSERT INTO game_events VALUES (?, ?, ?, ?, ?)", events)
    con.commit()
    con.close()

    # Create Spawns DB
    print(f"Creating Spawns DB at {SPAWNS_DB_PATH}")
    con = sqlite3.connect(SPAWNS_DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE spawns (
            RowName TEXT,
            Name TEXT
        )
    """)

    spawns = []
    for i in range(50):
        spawns.append((f"NPC_{i}", f"Monster {i}"))

    cur.executemany("INSERT INTO spawns VALUES (?, ?)", spawns)
    con.commit()
    con.close()

async def monitor_event_loop_lag(stop_event, interval=0.01):
    """Monitors event loop lag."""
    max_lag = 0
    total_lag = 0
    count = 0

    while not stop_event.is_set():
        start = time.perf_counter()
        await asyncio.sleep(interval)
        actual_duration = time.perf_counter() - start
        lag = actual_duration - interval
        if lag < 0: lag = 0

        if lag > max_lag:
            max_lag = lag
        total_lag += lag
        count += 1

    avg_lag = total_lag / count if count > 0 else 0
    return max_lag, avg_lag

async def main():
    setup_databases()

    # Mock Bot
    bot = MagicMock()
    bot._ = lambda x: x # Mock translation

    # Mock channel and send method
    mock_channel = MagicMock()
    # send needs to be awaitable
    async def async_send(*args, **kwargs):
        await asyncio.sleep(0.0001)
        return MagicMock()

    mock_channel.send = AsyncMock(side_effect=async_send)
    bot.get_channel.return_value = mock_channel

    cog = KillfeedCog(bot)

    # Stop the background tasks so we can run manually
    cog.kill_check_task.cancel()
    cog.ranking_update_task.cancel()
    cog.unified_ranking_task.cancel()

    print("Starting benchmark...")

    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_event_loop_lag(stop_event))

    start_time = time.perf_counter()

    # Run the function under test
    # We need to make sure it actually processes the events.
    # The code reads from LAST_EVENT_FILE (0) and queries > 0.
    # We inserted events starting at 100.
    await cog._process_server_kills(config.SERVERS[0])

    end_time = time.perf_counter()
    stop_event.set()
    max_lag, avg_lag = await monitor_task

    print(f"Total Execution Time: {end_time - start_time:.4f}s")
    print(f"Max Event Loop Lag: {max_lag:.4f}s")
    print(f"Avg Event Loop Lag: {avg_lag:.4f}s")

    # Check if we actually processed events
    # The channel.send should have been called
    print(f"Messages sent: {mock_channel.send.call_count}")

    # Cleanup
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

if __name__ == "__main__":
    asyncio.run(main())
