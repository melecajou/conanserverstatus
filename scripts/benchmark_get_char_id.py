import asyncio
import time
import sqlite3
import os
import sys
import aiosqlite

# Add the parent directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_char_id_by_name

DB_PATH = "benchmark_char_id.db"
NUM_CHARACTERS = 1000

def setup_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT)")
        for i in range(NUM_CHARACTERS):
            cur.execute("INSERT INTO characters (char_name) VALUES (?)", (f"Char_{i}",))
        con.commit()

def cleanup_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

async def monitor_loop(duration_container):
    max_block_time = 0
    while True:
        start = time.perf_counter()
        try:
            await asyncio.sleep(0.001)
        except asyncio.CancelledError:
            break
        end = time.perf_counter()
        elapsed = end - start
        block_time = elapsed - 0.001
        if block_time > max_block_time:
            max_block_time = block_time
    duration_container['max_block_time'] = max_block_time

async def run_to_thread_benchmark(iterations=100):
    print(f"Running benchmark: asyncio.to_thread(get_char_id_by_name) x {iterations}")
    metrics = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop(metrics))

    start_time = time.perf_counter()
    for i in range(iterations):
        char_name = f"Char_{i % NUM_CHARACTERS}"
        await asyncio.to_thread(get_char_id_by_name, DB_PATH, char_name)
    end_time = time.perf_counter()

    monitor_task.cancel()
    await asyncio.gather(monitor_task, return_exceptions=True)

    total_time = end_time - start_time
    print(f"Total Time: {total_time:.4f}s")
    print(f"Average Time: {total_time/iterations:.6f}s")
    print(f"Max Loop Block Time: {metrics['max_block_time']:.6f}s")
    return total_time, metrics['max_block_time']

async def async_get_char_id_by_name(db_path: str, char_name: str):
    if not os.path.exists(db_path):
        return None
    try:
        async with aiosqlite.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            async with con.execute("SELECT id FROM characters WHERE char_name = ?", (char_name,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None

async def run_native_async_benchmark(iterations=100):
    print(f"\nRunning benchmark: native async_get_char_id_by_name x {iterations}")
    metrics = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop(metrics))

    start_time = time.perf_counter()
    for i in range(iterations):
        char_name = f"Char_{i % NUM_CHARACTERS}"
        await async_get_char_id_by_name(DB_PATH, char_name)
    end_time = time.perf_counter()

    monitor_task.cancel()
    await asyncio.gather(monitor_task, return_exceptions=True)

    total_time = end_time - start_time
    print(f"Total Time: {total_time:.4f}s")
    print(f"Average Time: {total_time/iterations:.6f}s")
    print(f"Max Loop Block Time: {metrics['max_block_time']:.6f}s")
    return total_time, metrics['max_block_time']

async def main():
    setup_db()
    try:
        to_thread_total, to_thread_block = await run_to_thread_benchmark(200)
        async_total, async_block = await run_native_async_benchmark(200)

        print("\n--- Summary ---")
        print(f"to_thread Total: {to_thread_total:.4f}s")
        print(f"native async Total: {async_total:.4f}s")
        print(f"Improvement: {(to_thread_total - async_total) / to_thread_total * 100:.2f}%")
    finally:
        cleanup_db()

if __name__ == "__main__":
    asyncio.run(main())
