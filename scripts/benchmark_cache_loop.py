import time
import sys
import os
import sqlite3

# Add the root directory to sys.path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.database import get_global_player_data, _GLOBAL_PLAYER_CACHE, initialize_global_db, GLOBAL_DB_PATH

def benchmark():
    # Setup
    db_path = "data/test_global_registry.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    initialize_global_db(db_path)

    # Fill cache with many entries to make the O(N) list comprehension slow
    # We use a large number of entries to amplify the O(N^2) effect
    num_cache_entries = 10000
    now = time.time()
    _GLOBAL_PLAYER_CACHE.clear()
    for i in range(num_cache_entries):
        _GLOBAL_PLAYER_CACHE[(f"pid_{i}", db_path)] = {
            "data": {"discord_id": i, "vip_level": 0, "vip_expiry": None},
            "timestamp": now - 1000 # old timestamp
        }

    # IDs to query that are NOT in DB and NOT in cache with current timestamp
    num_queries = 1000
    pids_to_query = [f"missing_{i}" for i in range(num_queries)]

    # We want to measure only the function execution time
    start_time = time.time()
    get_global_player_data(pids_to_query, global_db_path=db_path)
    end_time = time.time()

    duration = end_time - start_time
    print(f"Time taken for {num_queries} queries with {num_cache_entries} cache entries: {duration:.4f} seconds")

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    benchmark()
