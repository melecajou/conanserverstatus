import asyncio
import time
import sqlite3
import os
import sys

# Add the parent directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import find_discord_user_by_char_name

GAME_DB_PATH = "benchmark_finduser_game.db"
GLOBAL_DB_PATH = "benchmark_finduser_global.db"
NUM_CHARACTERS = 1000

def setup_db():
    if os.path.exists(GAME_DB_PATH):
        os.remove(GAME_DB_PATH)
    if os.path.exists(GLOBAL_DB_PATH):
        os.remove(GLOBAL_DB_PATH)

    # Setup Game DB
    with sqlite3.connect(GAME_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT, playerId TEXT, guild INTEGER)")
        cur.execute("CREATE TABLE account (id TEXT PRIMARY KEY, platformId TEXT, user TEXT)")

        # Insert dummy data
        for i in range(NUM_CHARACTERS):
            char_name = f"TargetChar_{i}"
            player_id = f"PID_{i}"
            platform_id = f"Steam_{i}"
            cur.execute("INSERT INTO characters (char_name, playerId) VALUES (?, ?)", (char_name, player_id))
            cur.execute("INSERT INTO account (id, platformId) VALUES (?, ?)", (player_id, platform_id))
        con.commit()

    # Setup Global DB
    with sqlite3.connect(GLOBAL_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_identities (
                platform_id TEXT PRIMARY KEY,
                discord_id INTEGER NOT NULL
            )
        """)

        # Insert dummy data
        for i in range(NUM_CHARACTERS):
            platform_id = f"Steam_{i}"
            discord_id = 123456789 + i
            cur.execute("INSERT INTO user_identities (platform_id, discord_id) VALUES (?, ?)", (platform_id, discord_id))
        con.commit()


def cleanup_db():
    if os.path.exists(GAME_DB_PATH):
        os.remove(GAME_DB_PATH)
    if os.path.exists(GLOBAL_DB_PATH):
        os.remove(GLOBAL_DB_PATH)

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
    print("Running Blocking Version of finduser...")

    metrics = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop_blocking(metrics))

    start_time = time.perf_counter()

    # Simulate finding multiple characters
    for i in range(100):
        target = f"TargetChar_{i * 10}" # Look up a few spaced out
        result = find_discord_user_by_char_name(GAME_DB_PATH, target, GLOBAL_DB_PATH)
        # Yield control briefly
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
    print("\nRunning Non-Blocking (Async) Version of finduser...")

    metrics = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop_blocking(metrics))

    start_time = time.perf_counter()

    for i in range(100):
        target = f"TargetChar_{i * 10}"
        result = await asyncio.to_thread(find_discord_user_by_char_name, GAME_DB_PATH, target, GLOBAL_DB_PATH)
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
    setup_db()

    blocking_max = await run_blocking_version()
    non_blocking_max = await run_non_blocking_version()

    cleanup_db()

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
