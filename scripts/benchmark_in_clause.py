import sys
import os
import time
import sqlite3
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_global_player_data, initialize_global_db, get_batch_player_data, get_batch_player_levels

DB_PATH = "data/test_global_registry.db"
PLAYER_DB = "data/test_player_db.db"
GAME_DB = "data/test_game_db.db"

def setup_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(PLAYER_DB):
        os.remove(PLAYER_DB)
    if os.path.exists(GAME_DB):
        os.remove(GAME_DB)

    initialize_global_db(DB_PATH)

    with sqlite3.connect(PLAYER_DB) as con:
        con.execute("CREATE TABLE player_time (platform_id TEXT, server_name TEXT, online_minutes INT, discord_id TEXT)")
        for i in range(100):
            con.execute("INSERT INTO player_time VALUES (?, 'test_server', 100, '123')", (f"PLATFORM_{i}",))
        con.commit()

    with sqlite3.connect(GAME_DB) as con:
        con.execute("CREATE TABLE characters (char_name TEXT, level INT)")
        for i in range(100):
            con.execute("INSERT INTO characters VALUES (?, 50)", (f"CHAR_{i}",))
        con.commit()

    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        data = []
        for i in range(100):
            data.append((f"PLATFORM_{i}", i))
        cur.executemany("INSERT INTO user_identities (platform_id, discord_id) VALUES (?, ?)", data)
        con.commit()

def run_benchmark():
    # 100 unique items, repeated 100 times = 10000 items
    base_ids = [f"PLATFORM_{i}" for i in range(100)]
    platform_ids = base_ids * 100

    char_names = [f"CHAR_{i}" for i in range(100)] * 100

    start_time = time.perf_counter()
    for _ in range(50):
        get_global_player_data(platform_ids, DB_PATH)
    end_time = time.perf_counter()
    print(f"get_global_player_data baseline: {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(50):
        get_batch_player_data(PLAYER_DB, platform_ids, "test_server")
    end_time = time.perf_counter()
    print(f"get_batch_player_data baseline: {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(50):
        get_batch_player_levels(GAME_DB, char_names)
    end_time = time.perf_counter()
    print(f"get_batch_player_levels baseline: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    setup_db()
    run_benchmark()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(PLAYER_DB):
        os.remove(PLAYER_DB)
    if os.path.exists(GAME_DB):
        os.remove(GAME_DB)
