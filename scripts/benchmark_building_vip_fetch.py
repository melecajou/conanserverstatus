import time
import os
import sys
import sqlite3

# Add parent directory to path so we can import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import initialize_global_db, get_global_player_data, _GLOBAL_PLAYER_CACHE

DB_PATH = "scripts/test_global_registry.db"

def setup_db(num_users=10000):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    initialize_global_db(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Generate data
    identities = [(f"PLATFORM_{i}", i) for i in range(num_users)]
    vips = [(i, (i % 3) + 1, None) for i in range(num_users)] # Give everyone a VIP level

    cur.executemany("INSERT INTO user_identities (platform_id, discord_id) VALUES (?, ?)", identities)
    cur.executemany("INSERT INTO discord_vips (discord_id, vip_level, vip_expiry_date) VALUES (?, ?, ?)", vips)

    con.commit()
    con.close()
    return [f"PLATFORM_{i}" for i in range(num_users)]

def bench_current(platform_ids):
    _GLOBAL_PLAYER_CACHE.clear()

    start = time.time()
    platform_vip_map = {}
    if platform_ids:
        for i in range(0, len(platform_ids), 900):
            batch = platform_ids[i : i + 900]
            data = get_global_player_data(batch, global_db_path=DB_PATH)
            for platform_id, info in data.items():
                platform_vip_map[platform_id] = info.get("vip_level", 0)
    end = time.time()

    return end - start, len(platform_vip_map)

def bench_optimized(platform_ids):
    _GLOBAL_PLAYER_CACHE.clear()

    start = time.time()
    platform_vip_map = {}
    if platform_ids:
        data = get_global_player_data(platform_ids, global_db_path=DB_PATH)
        for platform_id, info in data.items():
            platform_vip_map[platform_id] = info.get("vip_level", 0)
    end = time.time()

    return end - start, len(platform_vip_map)

if __name__ == "__main__":
    print("Setting up test database...")
    platform_ids = setup_db(num_users=20000)

    # Let's run it multiple times to get an average
    num_runs = 5

    print(f"Benchmarking with {len(platform_ids)} platform IDs...")

    current_times = []
    for _ in range(num_runs):
        t, count = bench_current(platform_ids)
        current_times.append(t)

    avg_current = sum(current_times) / num_runs
    print(f"Current (Chunked outside): {avg_current:.4f}s avg over {num_runs} runs (Processed {count})")

    opt_times = []
    for _ in range(num_runs):
        t, count = bench_optimized(platform_ids)
        opt_times.append(t)

    avg_opt = sum(opt_times) / num_runs
    print(f"Optimized (Passed directly): {avg_opt:.4f}s avg over {num_runs} runs (Processed {count})")

    if avg_opt < avg_current:
        improvement = (avg_current - avg_opt) / avg_current * 100
        print(f"Improvement: {improvement:.2f}% faster")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
