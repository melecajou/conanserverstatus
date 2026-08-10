import asyncio
import time
import sqlite3
import os
import sys
import statistics

# Add the parent directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import link_discord_to_character

GAME_DB_PATH = "benchmark_game.db"
PLAYER_DB_PATH = "benchmark_playertracker.db"
SERVER_NAME = "BenchmarkServer"
NUM_CHARACTERS = 100

def setup_dbs():
    if os.path.exists(GAME_DB_PATH):
        os.remove(GAME_DB_PATH)
    if os.path.exists(PLAYER_DB_PATH):
        os.remove(PLAYER_DB_PATH)

    # Setup Game DB
    with sqlite3.connect(GAME_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT, playerId TEXT, guild INTEGER)")
        cur.execute("CREATE TABLE account (id TEXT PRIMARY KEY, platformId TEXT, user TEXT)")

        # Insert dummy data
        for i in range(NUM_CHARACTERS):
            char_name = f"Char_{i}"
            player_id = f"PID_{i}"
            platform_id = f"Steam_{i}"
            cur.execute("INSERT INTO characters (char_name, playerId) VALUES (?, ?)", (char_name, player_id))
            cur.execute("INSERT INTO account (id, platformId) VALUES (?, ?)", (player_id, platform_id))
        con.commit()

    # Setup Player Tracker DB
    with sqlite3.connect(PLAYER_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_time (
                platform_id TEXT NOT NULL,
                server_name TEXT NOT NULL,
                online_minutes INTEGER DEFAULT 0,
                last_rewarded_hour INTEGER DEFAULT 0,
                discord_id TEXT,
                PRIMARY KEY (platform_id, server_name)
            )
        """)
        con.commit()

def cleanup_dbs():
    if os.path.exists(GAME_DB_PATH):
        os.remove(GAME_DB_PATH)
    if os.path.exists(PLAYER_DB_PATH):
        os.remove(PLAYER_DB_PATH)

async def monitor_loop_blocking(duration_container):
    """Monitors the event loop blocking time."""
    max_block_time = 0
    while True:
        start = time.perf_counter()
        try:
            await asyncio.sleep(0.001)  # Sleep for 1ms
        except asyncio.CancelledError:
            break
        end = time.perf_counter()

        # Calculate how long the sleep actually took
        elapsed = end - start
        block_time = elapsed - 0.001
        if block_time > max_block_time:
            max_block_time = block_time

    duration_container['max_block_time'] = max_block_time

async def run_blocking_version():
    """Runs the synchronous version."""
    print("Running Blocking Version...")

    # Reset DB for fair comparison (though update is idempotentish here)
    setup_dbs()

    metrics = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop_blocking(metrics))

    start_time = time.perf_counter()

    # Simulate processing multiple registrations
    for i in range(NUM_CHARACTERS):
        link_discord_to_character(
            PLAYER_DB_PATH,
            GAME_DB_PATH,
            SERVER_NAME,
            123456789 + i,
            f"Char_{i}"
        )
        # Yield control briefly to simulate other tasks, but the call itself is blocking
        await asyncio.sleep(0)

    end_time = time.perf_counter()
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    print(f"Total Time: {end_time - start_time:.4f}s")
    print(f"Max Loop Block Time: {metrics['max_block_time']:.4f}s")
    return metrics['max_block_time']

async def run_non_blocking_version():
    """Runs the asynchronous version using to_thread."""
    print("\nRunning Non-Blocking (Async) Version...")

    setup_dbs()

    metrics = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop_blocking(metrics))

    start_time = time.perf_counter()

    for i in range(NUM_CHARACTERS):
        # The optimization: wrap in to_thread
        await asyncio.to_thread(
            link_discord_to_character,
            PLAYER_DB_PATH,
            GAME_DB_PATH,
            SERVER_NAME,
            123456789 + i,
            f"Char_{i}"
        )
        await asyncio.sleep(0)

    end_time = time.perf_counter()
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    print(f"Total Time: {end_time - start_time:.4f}s")
    print(f"Max Loop Block Time: {metrics['max_block_time']:.4f}s")
    return metrics['max_block_time']

async def main():
    # Setup initial DBs
    setup_dbs()

    blocking_max = await run_blocking_version()
    non_blocking_max = await run_non_blocking_version()

    cleanup_dbs()

    print("\n--- Results ---")
    print(f"Blocking Max Delay: {blocking_max:.6f}s")
    print(f"Non-Blocking Max Delay: {non_blocking_max:.6f}s")

    if blocking_max > 0:
        improvement = (blocking_max - non_blocking_max) / blocking_max * 100
        print(f"Responsiveness Improvement: {improvement:.2f}%")
    else:
        print("Could not measure blocking time (too fast?)")

if __name__ == "__main__":
    asyncio.run(main())
