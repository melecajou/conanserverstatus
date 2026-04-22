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
TEMP_DIR = os.path.join(PROJECT_ROOT, "temp_killfeed_task_bench2")

class MockConfig:
    KILLFEED_SPAWNS_DB = os.path.join(TEMP_DIR, "spawns.db")
    KILLFEED_RANKING_DB = os.path.join(TEMP_DIR, "ranking.db")
    KILLFEED_STATE_FILE = os.path.join(TEMP_DIR, "ranking_state.json")
    SERVERS = []
    KILLFEED_UNIFIED_RANKINGS = []

# Inject mock config
sys.modules["config"] = MockConfig
import config
from cogs.killfeed import KillfeedCog

# Set up logging
logging.basicConfig(level=logging.ERROR)

def setup_servers(num_servers=5):
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    config.SERVERS = []

    for i in range(num_servers):
        server_name = f"Server_{i}"
        db_path = os.path.join(TEMP_DIR, f"game_{i}.db")
        last_event_file = os.path.join(TEMP_DIR, f"last_event_{i}.txt")

        with open(last_event_file, "w") as f:
            f.write("0")

        # Create Game DB
        con = sqlite3.connect(db_path)
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

        # Add 1000 events to each server to simulate some work
        events = []
        for j in range(1000):
            world_time = 100 + j
            event_type = 103
            causer_name = f"Killer_{j}"
            owner_name = f"Owner_{j}"
            args_map = json.dumps({"nonPersistentCauser": None})
            events.append((world_time, event_type, causer_name, owner_name, args_map))
        cur.executemany("INSERT INTO game_events VALUES (?, ?, ?, ?, ?)", events)
        con.commit()
        con.close()

        config.SERVERS.append({
            "NAME": server_name,
            "DB_PATH": db_path,
            "KILLFEED_CONFIG": {
                "ENABLED": True,
                "CHANNEL_ID": 123 + i,
                "RANKING_CHANNEL_ID": 456 + i,
                "LAST_EVENT_FILE": last_event_file,
                "PVP_ONLY": False
            }
        })

    # Create Spawns DB
    con = sqlite3.connect(config.KILLFEED_SPAWNS_DB)
    cur = con.cursor()
    cur.execute("CREATE TABLE spawns (RowName TEXT, Name TEXT)")
    con.commit()
    con.close()

async def main():
    setup_servers(10) # Test with 10 servers

    bot = MagicMock()
    bot._ = lambda x: x
    mock_channel = MagicMock()

    async def async_send(*args, **kwargs):
        # simulate brief I/O delay sending a message
        await asyncio.sleep(0.0001)
        return MagicMock()

    mock_channel.send = AsyncMock(side_effect=async_send)
    bot.get_channel.return_value = mock_channel

    cog = KillfeedCog(bot)
    cog.kill_check_task.cancel()
    cog.ranking_update_task.cancel()
    cog.unified_ranking_task.cancel()

    # Apply optimization
    async def new_kill_check_task():
        async def safe_process(server_conf):
            try:
                await cog._process_server_kills(server_conf)
            except Exception as e:
                pass

        tasks = []
        for server_conf in config.SERVERS:
            kf_config = server_conf.get("KILLFEED_CONFIG")
            if not kf_config or not kf_config.get("ENABLED"):
                continue
            tasks.append(safe_process(server_conf))

        if tasks:
            await asyncio.gather(*tasks)

    print(f"Benchmarking GATHER kill_check_task over {len(config.SERVERS)} servers...")

    start_time = time.perf_counter()
    await new_kill_check_task()
    end_time = time.perf_counter()

    print(f"Total Execution Time: {end_time - start_time:.4f}s")
    print(f"Messages sent: {mock_channel.send.call_count}")

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)

if __name__ == "__main__":
    asyncio.run(main())
