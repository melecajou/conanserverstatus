import sys
import os
import time
import sqlite3
from typing import List, Dict, Any, Optional
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import initialize_global_db

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

# --- OPTIMIZED FUNCTIONS ---

def opt_get_global_player_data(
    platform_ids: List[str], global_db_path: str = DB_PATH
) -> Dict[str, Dict[str, Any]]:
    data = {
        pid: {"discord_id": None, "vip_level": 0, "vip_expiry": None}
        for pid in platform_ids
    }
    if not platform_ids:
        return data

    unique_platform_ids = list(set(platform_ids))

    try:
        with sqlite3.connect(f"file:{global_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            placeholders = ", ".join("?" * len(unique_platform_ids))

            query = f"""
                SELECT ui.platform_id, ui.discord_id, dv.vip_level, dv.vip_expiry_date
                FROM user_identities ui
                LEFT JOIN discord_vips dv ON ui.discord_id = dv.discord_id
                WHERE ui.platform_id IN ({placeholders})
            """
            cur.execute(query, unique_platform_ids)
            for pid, discord_id, vip_level, vip_expiry in cur.fetchall():
                data[pid] = {
                    "discord_id": discord_id,
                    "vip_level": vip_level if vip_level else 0,
                    "vip_expiry": vip_expiry,
                }
    except Exception as e:
        pass
    return data

def opt_get_batch_player_levels(
    db_path: str, char_names: List[str]
) -> Optional[Dict[str, int]]:
    levels = {name: 0 for name in char_names}
    if not db_path or not char_names:
        return levels

    unique_char_names = list(set(char_names))

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            placeholders = ", ".join("?" * len(unique_char_names))
            cur.execute(
                f"SELECT char_name, level FROM characters WHERE char_name IN ({placeholders})",
                unique_char_names,
            )
            for name, level in cur.fetchall():
                levels[name] = level
    except sqlite3.DatabaseError:
        return None
    except Exception as e:
        return None
    return levels

def opt_get_batch_player_data(
    db_path: str, platform_ids: List[str], server_name: str
) -> Dict[str, Dict[str, Any]]:
    player_data = {
        pid: {"online_minutes": 0, "is_registered": False} for pid in platform_ids
    }
    if not platform_ids:
        return player_data

    unique_platform_ids = list(set(platform_ids))

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            placeholders = ", ".join("?" * len(unique_platform_ids))
            query_params = unique_platform_ids + [server_name]
            cur.execute(
                f"SELECT platform_id, online_minutes, discord_id FROM player_time WHERE platform_id IN ({placeholders}) AND server_name = ?",
                query_params,
            )
            for pid, minutes, discord_id in cur.fetchall():
                player_data[pid]["online_minutes"] = minutes
                player_data[pid]["is_registered"] = bool(discord_id)
    except Exception as e:
        pass
    return player_data

def run_benchmark():
    # 100 unique items, repeated 100 times = 10000 items
    base_ids = [f"PLATFORM_{i}" for i in range(100)]
    platform_ids = base_ids * 100

    char_names = [f"CHAR_{i}" for i in range(100)] * 100

    start_time = time.perf_counter()
    for _ in range(50):
        opt_get_global_player_data(platform_ids, DB_PATH)
    end_time = time.perf_counter()
    print(f"opt_get_global_player_data: {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(50):
        opt_get_batch_player_data(PLAYER_DB, platform_ids, "test_server")
    end_time = time.perf_counter()
    print(f"opt_get_batch_player_data: {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(50):
        opt_get_batch_player_levels(GAME_DB, char_names)
    end_time = time.perf_counter()
    print(f"opt_get_batch_player_levels: {end_time - start_time:.4f} seconds")

if __name__ == "__main__":
    setup_db()
    run_benchmark()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(PLAYER_DB):
        os.remove(PLAYER_DB)
    if os.path.exists(GAME_DB):
        os.remove(GAME_DB)
