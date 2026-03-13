import asyncio
import time
import sqlite3

def create_mock_db():
    conn = sqlite3.connect("mock_db.sqlite")
    conn.execute("CREATE TABLE IF NOT EXISTS item_inventory (owner_id INTEGER, item_id INTEGER, inv_type INTEGER, template_id INTEGER)")
    conn.execute("DELETE FROM item_inventory") # cleanup
    # Insert initial rows
    for i in range(10):
        conn.execute("INSERT INTO item_inventory VALUES (?, ?, ?, ?)", (1, i, 0, 100))
    conn.commit()
    conn.close()

async def simulate_finding_item(before_items, delay_before_insert):
    start_time = time.time()
    db_path = "mock_db.sqlite"
    char_id = 1
    template_id = 999

    import aiosqlite

    # Background task to insert the item after a delay
    async def insert_item_later():
        await asyncio.sleep(delay_before_insert)
        async with aiosqlite.connect(f"file:{db_path}", uri=True) as con:
            await con.execute("INSERT INTO item_inventory VALUES (?, ?, ?, ?)", (1, 10, 0, 999))
            await con.commit()

    asyncio.create_task(insert_item_later())

    new_item_found = None

    # NEW OPTIMIZED LOGIC
    # Wait for the item to appear or loop times out
    # Instead of static sleep, we can poll
    for attempt in range(18):  # Try more frequently
        async with aiosqlite.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            async with con.execute(
                "SELECT item_id, inv_type, template_id FROM item_inventory WHERE owner_id=? AND template_id=?",
                (char_id, template_id),
            ) as cur:
                after_rows = await cur.fetchall()

        for row in after_rows:
            key = (row[0], row[1])
            if key not in before_items:
                new_item_found = key
                break

        if new_item_found:
            break

        if not new_item_found:
            for row in after_rows:
                key = (row[0], row[1])
                new_item_found = key
                break

        if new_item_found:
            break

        await asyncio.sleep(1) # wait 1s

    elapsed = time.time() - start_time
    print(f"Elapsed: {elapsed:.4f}s")
    print(f"Found: {new_item_found}")
    return elapsed

async def main():
    import os
    if os.path.exists("mock_db.sqlite"):
        os.remove("mock_db.sqlite")
    create_mock_db()
    before_items = {(i, 0): 100 for i in range(10)}
    print("Testing with 0s delay (immediate insert):")
    await simulate_finding_item(before_items, 0.0)

    # Clean up and test with 2s delay
    if os.path.exists("mock_db.sqlite"):
        os.remove("mock_db.sqlite")
    create_mock_db()
    print("Testing with 2s delay:")
    await simulate_finding_item(before_items, 2.0)

    if os.path.exists("mock_db.sqlite"):
        os.remove("mock_db.sqlite")

if __name__ == "__main__":
    asyncio.run(main())
