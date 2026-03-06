import time
import sqlite3
import os
import sys

# Add the parent directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import link_discord_to_character

GAME_DB_PATH = "benchmark_link_game.db"
PLAYER_TRACKER_DB_PATH = "benchmark_link_tracker.db"
NUM_CHARACTERS = 10000

def setup_db():
    if os.path.exists(GAME_DB_PATH):
        os.remove(GAME_DB_PATH)
    if os.path.exists(PLAYER_TRACKER_DB_PATH):
        os.remove(PLAYER_TRACKER_DB_PATH)

    # Setup Game DB
    with sqlite3.connect(GAME_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT, playerId TEXT)")
        cur.execute("CREATE TABLE account (id TEXT PRIMARY KEY, platformId TEXT)")

        # Insert dummy data
        data_chars = []
        data_accounts = []
        for i in range(NUM_CHARACTERS):
            char_name = f"Char_{i}"
            player_id = f"PID_{i}"
            platform_id = f"Platform_{i}"
            data_chars.append((char_name, player_id))
            data_accounts.append((player_id, platform_id))

        cur.executemany("INSERT INTO characters (char_name, playerId) VALUES (?, ?)", data_chars)
        cur.executemany("INSERT INTO account (id, platformId) VALUES (?, ?)", data_accounts)
        con.commit()

    # Setup Player Tracker DB
    with sqlite3.connect(PLAYER_TRACKER_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_time (
                platform_id TEXT NOT NULL,
                server_name TEXT NOT NULL,
                discord_id TEXT,
                PRIMARY KEY (platform_id, server_name)
            )
        """)
        con.commit()

def cleanup_db():
    if os.path.exists(GAME_DB_PATH):
        os.remove(GAME_DB_PATH)
    if os.path.exists(PLAYER_TRACKER_DB_PATH):
        os.remove(PLAYER_TRACKER_DB_PATH)

def run_benchmark(iterations=1000):
    print(f"Running benchmark with {iterations} iterations...")
    start_time = time.perf_counter()
    for i in range(iterations):
        char_name = f"Char_{i % NUM_CHARACTERS}"
        link_discord_to_character(PLAYER_TRACKER_DB_PATH, GAME_DB_PATH, "test_server", 123456789, char_name)
    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time = total_time / iterations
    print(f"Total Time: {total_time:.4f}s")
    print(f"Average Time per call: {avg_time:.6f}s")
    return total_time

if __name__ == "__main__":
    setup_db()
    try:
        run_benchmark()
    finally:
        cleanup_db()
