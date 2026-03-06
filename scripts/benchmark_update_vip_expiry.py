import time
import os
import sqlite3
from utils.database import initialize_global_db, update_vip_expiry, set_global_vip

DB_PATH = "test_benchmark.db"

def setup_db(num_users):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    initialize_global_db(DB_PATH)

    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        batch = [(i, 1, "2024-01-01T00:00:00") for i in range(1, num_users + 1)]
        cur.executemany(
            "INSERT INTO discord_vips (discord_id, vip_level, vip_expiry_date) VALUES (?, ?, ?)",
            batch
        )
        con.commit()

def run_benchmark(iterations, target_id):
    start_time = time.perf_counter()
    for _ in range(iterations):
        update_vip_expiry(target_id, 30, DB_PATH)
    end_time = time.perf_counter()
    return end_time - start_time

if __name__ == "__main__":
    print("Setting up database...")
    setup_db(10000)

    iterations = 1000
    target_id = 5000  # Existing user

    print(f"Running benchmark with {iterations} iterations on existing user...")
    time_taken = run_benchmark(iterations, target_id)
    print(f"Total time: {time_taken:.4f}s")
    print(f"Average time per call: {(time_taken / iterations) * 1000:.4f}ms")

    target_id = 999999  # Non-existing user
    print(f"\nRunning benchmark with {iterations} iterations on non-existing user...")
    time_taken_non_existing = run_benchmark(iterations, target_id)
    print(f"Total time: {time_taken_non_existing:.4f}s")
    print(f"Average time per call: {(time_taken_non_existing / iterations) * 1000:.4f}ms")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
