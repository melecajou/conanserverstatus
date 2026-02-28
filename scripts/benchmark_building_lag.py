import asyncio
import sqlite3
import os
import sys
import time

DB_PATH = "scripts/reproduce_building_game.db"
SQL_PATH = "scripts/buildings.sql"

def setup_db(count=50000):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("CREATE TABLE buildings (owner_id INTEGER, pieces INTEGER)")

    # Create a lot of data to ensure the query takes time
    print(f"Generating {count} records...")

    for i in range(1, count + 1):
        cur.execute("INSERT INTO buildings (owner_id, pieces) VALUES (?, ?)", (i % 500, i % 10))

    con.commit()
    con.close()

    with open(SQL_PATH, "w") as f:
        f.write("SELECT owner_id, SUM(pieces) FROM buildings GROUP BY owner_id ORDER BY SUM(pieces) DESC;")

async def heartbeat(monitor_duration):
    """Monitors the event loop lag."""
    print("Heartbeat started")
    start_time = time.time()
    max_lag = 0
    last_beat = start_time

    while time.time() - start_time < monitor_duration:
        await asyncio.sleep(0.01) # Sleep for 10ms
        now = time.time()
        # Expected duration is 0.01s. Lag is anything above that.
        lag = (now - last_beat) - 0.01
        if lag > max_lag:
            max_lag = lag
        last_beat = now

    print(f"Heartbeat finished. Max lag: {max_lag*1000:.2f}ms")
    return max_lag

def sync_operation():
    with open(SQL_PATH, "r") as f:
        sql_script = f.read()
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as con:
        cur = con.cursor()
        cur.execute(sql_script)
        results = cur.fetchall()
    return results

async def main():
    setup_db(count=1000000)

    print("\n--- BASELINE: Synchronous Execution ---")

    monitor_task = asyncio.create_task(heartbeat(2.0))
    await asyncio.sleep(0.1)

    start = time.time()
    sync_operation()
    duration = time.time() - start

    print(f"Sync operation took {duration:.4f}s")
    max_lag = await monitor_task
    print(f"Baseline Max Loop Lag: {max_lag*1000:.2f}ms")


    print("\n--- VERIFICATION: asyncio.to_thread ---")

    monitor_task = asyncio.create_task(heartbeat(2.0))
    await asyncio.sleep(0.1)

    start = time.time()
    await asyncio.to_thread(sync_operation)
    duration = time.time() - start

    print(f"Threaded operation took {duration:.4f}s")
    max_lag_threaded = await monitor_task
    print(f"Threaded Max Loop Lag: {max_lag_threaded*1000:.2f}ms")

    # Cleanup
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(SQL_PATH):
        os.remove(SQL_PATH)

if __name__ == "__main__":
    asyncio.run(main())
