import asyncio
import aiosqlite
import time
import random
import os

# Define the table schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS player_time (
    platform_id TEXT NOT NULL,
    server_name TEXT NOT NULL,
    online_minutes INTEGER DEFAULT 0,
    last_rewarded_hour INTEGER DEFAULT 0,
    PRIMARY KEY (platform_id, server_name)
);
"""

SERVER_NAME = "BenchmarkServer"
NUM_PLAYERS = 100
NUM_ITERATIONS = 50

async def setup_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)

    db = await aiosqlite.connect(db_path)
    await db.execute(SCHEMA)
    await db.commit()
    return db

async def current_update_playtime(db, server_name, online_players):
    async with db.cursor() as cur:
        for player in online_players:
            platform_id = player["platform_id"]
            await cur.execute(
                "INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)",
                (platform_id, server_name),
            )
            await cur.execute(
                "UPDATE player_time SET online_minutes = online_minutes + 1 WHERE platform_id = ? AND server_name = ?",
                (platform_id, server_name),
            )
    await db.commit()

async def optimized_update_playtime(db, server_name, online_players):
    data = [(p["platform_id"], server_name) for p in online_players]
    if not data:
        return

    # Use ON CONFLICT to perform UPSERT
    # If the record exists (conflict on platform_id, server_name), increment online_minutes
    # If not, insert with online_minutes = 1 (default 0 + 1)
    # Wait, default is 0. If we insert, we want it to be 1 (0 initial + 1 minute)
    # So VALUES (?, ?, 1)
    await db.executemany(
        """
        INSERT INTO player_time (platform_id, server_name, online_minutes)
        VALUES (?, ?, 1)
        ON CONFLICT(platform_id, server_name)
        DO UPDATE SET online_minutes = online_minutes + 1
        """,
        data,
    )
    await db.commit()

async def run_benchmark():
    print(f"Benchmarking with {NUM_PLAYERS} players over {NUM_ITERATIONS} iterations...")

    online_players = [
        {"platform_id": f"player_{i}", "char_name": f"Char_{i}"}
        for i in range(NUM_PLAYERS)
    ]

    # Benchmark Current Implementation
    db_current = await setup_db("benchmark_current.db")
    start_time = time.time()
    for _ in range(NUM_ITERATIONS):
        await current_update_playtime(db_current, SERVER_NAME, online_players)
    end_time = time.time()
    current_duration = end_time - start_time
    await db_current.close()
    os.remove("benchmark_current.db")

    print(f"Current Implementation: {current_duration:.4f} seconds")

    # Benchmark Optimized Implementation
    db_optimized = await setup_db("benchmark_optimized.db")
    start_time = time.time()
    for _ in range(NUM_ITERATIONS):
        await optimized_update_playtime(db_optimized, SERVER_NAME, online_players)
    end_time = time.time()
    optimized_duration = end_time - start_time

    # Verify correctness (checking one record)
    async with db_optimized.execute("SELECT online_minutes FROM player_time WHERE platform_id = 'player_0'") as cur:
        row = await cur.fetchone()
        print(f"Verification: Player 0 online_minutes = {row[0]} (Expected {NUM_ITERATIONS})")

    await db_optimized.close()
    os.remove("benchmark_optimized.db")

    print(f"Optimized Implementation: {optimized_duration:.4f} seconds")

    improvement = current_duration - optimized_duration
    percent = (improvement / current_duration) * 100
    print(f"Improvement: {improvement:.4f} seconds ({percent:.2f}%)")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
