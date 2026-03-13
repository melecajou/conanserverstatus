import asyncio
import time
import sqlite3
import os
import sys

# Add the parent directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import find_discord_user_by_char_name

GAME_DB_PATH = "benchmark_finduser_cache_game.db"
GLOBAL_DB_PATH = "benchmark_finduser_cache_global.db"
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

def run_benchmark(iterations=100, repeat=10):
    """Runs the benchmark and returns the total time taken."""
    print(f"Running benchmark: {iterations} iterations, repeated {repeat} times (total {iterations * repeat} lookups)...")

    start_time = time.perf_counter()

    for _ in range(repeat):
        for i in range(iterations):
            target = f"TargetChar_{i}"
            result = find_discord_user_by_char_name(GAME_DB_PATH, target, GLOBAL_DB_PATH)

    end_time = time.perf_counter()
    total_time = end_time - start_time
    print(f"Total Time: {total_time:.4f}s")
    print(f"Average time per lookup: {(total_time / (iterations * repeat)) * 1000:.4f}ms")
    return total_time

def main():
    setup_db()
    try:
        run_benchmark()
    finally:
        cleanup_db()

if __name__ == "__main__":
    main()
