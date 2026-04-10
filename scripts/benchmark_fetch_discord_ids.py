import asyncio
import time
import sqlite3
import os
import sys
import threading

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PLAYER_DB_PATH = "benchmark_playertracker_fetch.db"
NUM_RECORDS = 500000

def setup_db():
    if os.path.exists(PLAYER_DB_PATH):
        os.remove(PLAYER_DB_PATH)

    with sqlite3.connect(PLAYER_DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_time (
                platform_id TEXT NOT NULL,
                server_name TEXT NOT NULL,
                online_minutes INTEGER DEFAULT 0,
                last_rewarded_hour INTEGER DEFAULT 0,
                discord_id TEXT,
                PRIMARY KEY (platform_id, server_name)
            )
        """)
        # Insert dummy data
        data = []
        for i in range(NUM_RECORDS):
            discord_id = str(1000000000 + i) if i % 2 == 0 else None
            data.append((f"Steam_{i}", "ServerA", discord_id))

        cur.executemany("INSERT INTO player_time (platform_id, server_name, discord_id) VALUES (?, ?, ?)", data)
        con.commit()

def cleanup_db():
    if os.path.exists(PLAYER_DB_PATH):
        os.remove(PLAYER_DB_PATH)

async def monitor_loop_blocking(duration_container):
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

# Original code (simulating no to_thread)
def _fetch_all_linked_discord_ids_sync(servers=None):
    linked_discord_ids = set()
    for server in servers:
        player_db = server.get("PLAYER_DB_PATH")
        if not player_db or not os.path.exists(player_db):
            continue

        try:
            with sqlite3.connect(player_db) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT discord_id FROM player_time WHERE discord_id IS NOT NULL"
                )
                rows = cursor.fetchall()
                for row in rows:
                    if row[0]:
                        try:
                            linked_discord_ids.add(int(row[0]))
                        except ValueError:
                            pass
        except Exception as e:
            print(f"Error reading DB {player_db}: {e}")
    return linked_discord_ids

# Using aiosqlite
async def _fetch_all_linked_discord_ids_async(servers=None):
    import aiosqlite
    linked_discord_ids = set()

    for server in servers:
        player_db = server.get("PLAYER_DB_PATH")
        if not player_db or not os.path.exists(player_db):
            continue

        try:
            async with aiosqlite.connect(player_db) as conn:
                async with conn.execute(
                    "SELECT DISTINCT discord_id FROM player_time WHERE discord_id IS NOT NULL"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        if row[0]:
                            try:
                                linked_discord_ids.add(int(row[0]))
                            except ValueError:
                                pass
        except Exception as e:
            print(f"Error reading DB {player_db}: {e}")

    return linked_discord_ids

async def wrapper_sync_blocking(servers, duration_container):
    monitor_task = asyncio.create_task(monitor_loop_blocking(duration_container))
    await asyncio.sleep(0.05) # ensure monitor starts

    start_time = time.perf_counter()
    # Execute the sync function directly, blocking the loop
    ids = _fetch_all_linked_discord_ids_sync(servers)
    end_time = time.perf_counter()

    monitor_task.cancel()
    try: await monitor_task
    except asyncio.CancelledError: pass

    # In single-threaded execution, the max block time might not be captured
    # by the monitor if the entire execution is one block.
    # We can approximate it as the total time taken by the function.
    if duration_container['max_block_time'] < (end_time - start_time):
         duration_container['max_block_time'] = end_time - start_time

    return ids, end_time - start_time

async def wrapper_to_thread(servers, duration_container):
    monitor_task = asyncio.create_task(monitor_loop_blocking(duration_container))
    await asyncio.sleep(0.05) # ensure monitor starts

    start_time = time.perf_counter()
    # Execute the sync function in a thread
    ids = await asyncio.to_thread(_fetch_all_linked_discord_ids_sync, servers)
    end_time = time.perf_counter()

    monitor_task.cancel()
    try: await monitor_task
    except asyncio.CancelledError: pass

    return ids, end_time - start_time

async def main():
    setup_db()
    servers = [{"PLAYER_DB_PATH": PLAYER_DB_PATH}]

    # 1. Test synchronous baseline directly in event loop (blocking)
    print("Running Blocking Baseline (sqlite3 directly in event loop)...")
    metrics_baseline = {'max_block_time': 0}
    ids_sync, time_sync = await wrapper_sync_blocking(servers, metrics_baseline)

    print(f"Total Time: {time_sync:.4f}s")
    print(f"Max Loop Block Time: {metrics_baseline['max_block_time']:.4f}s")
    sync_block_time = metrics_baseline['max_block_time']


    # 2. Test to_thread implementation
    print("\nRunning to_thread version (asyncio.to_thread)...")
    metrics_thread = {'max_block_time': 0}
    ids_thread, time_thread = await wrapper_to_thread(servers, metrics_thread)

    print(f"Total Time: {time_thread:.4f}s")
    print(f"Max Loop Block Time: {metrics_thread['max_block_time']:.4f}s")
    thread_block_time = metrics_thread['max_block_time']


    # 3. Test aiosqlite implementation
    print("\nRunning Async version (aiosqlite)...")
    metrics_async = {'max_block_time': 0}
    monitor_task = asyncio.create_task(monitor_loop_blocking(metrics_async))
    await asyncio.sleep(0.05)

    start_time = time.perf_counter()
    ids_async = await _fetch_all_linked_discord_ids_async(servers)
    end_time = time.perf_counter()

    monitor_task.cancel()
    try: await monitor_task
    except asyncio.CancelledError: pass

    print(f"Total Time: {end_time - start_time:.4f}s")
    print(f"Max Loop Block Time: {metrics_async['max_block_time']:.4f}s")
    async_block_time = metrics_async['max_block_time']


    cleanup_db()

    print("\n--- Results ---")
    print(f"Sync Blocking Max Delay: {sync_block_time:.6f}s")
    print(f"to_thread Max Delay: {thread_block_time:.6f}s")
    print(f"aiosqlite Max Delay: {async_block_time:.6f}s")
    if sync_block_time > 0:
        improvement_thread = (sync_block_time - thread_block_time) / sync_block_time * 100
        print(f"to_thread Responsiveness Improvement: {improvement_thread:.2f}%")
        improvement_async = (sync_block_time - async_block_time) / sync_block_time * 100
        print(f"aiosqlite Responsiveness Improvement: {improvement_async:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
