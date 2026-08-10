import time
import os
import sqlite3

def setup_db(db_path, num_guilds=50, num_chars=500):
    if os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("CREATE TABLE guilds (guildId INTEGER, name TEXT)")
    cur.execute("CREATE TABLE characters (id INTEGER, char_name TEXT, playerId TEXT, guild INTEGER)")

    guild_data = [(i, f"Guild {i}") for i in range(1, num_guilds + 1)]
    cur.executemany("INSERT INTO guilds VALUES (?, ?)", guild_data)

    char_data = [(i, f"Char {i}", f"pid_{i}", (i % num_guilds) + 1) for i in range(1, num_chars + 1)]
    cur.executemany("INSERT INTO characters VALUES (?, ?, ?, ?)", char_data)

    con.commit()
    con.close()

def bench_current(owner_ids, db_path):
    # simulate the logic
    guild_owners = {1: "Guild 1"} # mock

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    start = time.time()
    potential_player_ids = [oid for oid in owner_ids if oid not in guild_owners]
    player_owners = {}
    if potential_player_ids:
        for i in range(0, len(potential_player_ids), 900):
            batch = potential_player_ids[i : i + 900]
            placeholders = ",".join("?" * len(batch))
            cur.execute(
                f"SELECT id, char_name, playerId FROM characters WHERE id IN ({placeholders})",
                batch,
            )
            for char_id, name, pid in cur.fetchall():
                player_owners[char_id] = (name, pid)
    end = time.time()
    con.close()
    return end - start, len(potential_player_ids)

def bench_optimized(owner_ids, db_path):
    guild_owners = {1: "Guild 1"} # mock

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    start = time.time()
    # Deduplicate before chunking
    potential_player_ids = list(set([oid for oid in owner_ids if oid not in guild_owners]))
    player_owners = {}
    if potential_player_ids:
        for i in range(0, len(potential_player_ids), 32000):
            batch = potential_player_ids[i : i + 32000]
            placeholders = ",".join("?" * len(batch))
            cur.execute(
                f"SELECT id, char_name, playerId FROM characters WHERE id IN ({placeholders})",
                batch,
            )
            for char_id, name, pid in cur.fetchall():
                player_owners[char_id] = (name, pid)
    end = time.time()
    con.close()
    return end - start, len(potential_player_ids)

if __name__ == "__main__":
    db_path = "test_building.db"
    setup_db(db_path)

    # simulate lots of duplicate owner_ids, e.g. lots of building pieces owned by a few people
    owner_ids = [i % 500 for i in range(100000)]

    t1, count1 = bench_current(owner_ids, db_path)
    print(f"Current: {t1:.4f}s (list size {count1})")

    t2, count2 = bench_optimized(owner_ids, db_path)
    print(f"Optimized: {t2:.4f}s (list size {count2})")
