import asyncio
import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.database import get_global_player_data, _GLOBAL_PLAYER_CACHE, initialize_global_db, GLOBAL_DB_PATH

async def benchmark():
    db_path = "data/test_global_registry.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs("data", exist_ok=True)
    initialize_global_db(db_path)

    # Populate cache
    now = time.time()
    num_cache_entries = 100000
    for i in range(num_cache_entries):
        _GLOBAL_PLAYER_CACHE[(f"pid_{i}", db_path)] = {
            "data": {"discord_id": i, "vip_level": 0, "vip_expiry": None},
            "timestamp": now
        }

    # Generate a massive list of platform_ids with lots of duplicates to highlight
    # the issue. We're removing duplicates *before* the loop, rather than looping
    # over all of them.
    unique_pids = [f"pid_{i}" for i in range(1000)] + [f"missing_{i}" for i in range(1000)]
    pids_to_query = unique_pids * 500  # 1,000,000 items

    start_time = time.time()
    await get_global_player_data(pids_to_query, global_db_path=db_path)
    end_time = time.time()

    duration = end_time - start_time
    print(f"Time taken for {len(pids_to_query)} queries (with duplicates): {duration:.4f} seconds")

    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    asyncio.run(benchmark())
