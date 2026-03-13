import sqlite3
import time
import os

DB_PATH = "scripts/test_game.db"

def setup_db(num_guilds=5000, num_chars=200000):
    if os.path.exists(DB_PATH): os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("CREATE TABLE guilds (guildId INTEGER, name TEXT)")
    cur.execute("CREATE TABLE characters (id INTEGER, char_name TEXT, playerId TEXT, guild INTEGER)")

    print(f"Generating data: {num_guilds} guilds, {num_chars} chars")

    guild_data = [(i, f"Guild {i}") for i in range(1, num_guilds + 1)]
    cur.executemany("INSERT INTO guilds VALUES (?, ?)", guild_data)

    char_data = []
    for i in range(1, num_chars + 1):
        char_data.append((i, f"Char {i}", f"pid_{i}", (i % num_guilds) + 1))

    cur.executemany("INSERT INTO characters VALUES (?, ?, ?, ?)", char_data)

    cur.execute("CREATE INDEX idx_guild ON characters(guild)")
    cur.execute("CREATE INDEX idx_char_id ON characters(id)")

    con.commit()
    con.close()

def bench_in_clause(guild_ids):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    guild_members = {}

    start = time.time()
    for i in range(0, len(guild_ids), 900):
        batch = guild_ids[i : i + 900]
        placeholders = ",".join("?" * len(batch))
        cur.execute(
            f"SELECT guild, playerId FROM characters WHERE guild IN ({placeholders})",
            batch,
        )
        for gid, pid in cur.fetchall():
            if gid not in guild_members:
                guild_members[gid] = []
            guild_members[gid].append(pid)

    end = time.time()
    con.close()
    return end - start

def bench_single_in_clause(guild_ids):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    guild_members = {}
    start = time.time()
    for i in range(0, len(guild_ids), 32000):
        batch = guild_ids[i : i + 32000]
        placeholders = ",".join("?" * len(batch))
        cur.execute(f"SELECT guild, playerId FROM characters WHERE guild IN ({placeholders})", batch)
        for gid, pid in cur.fetchall():
            if gid not in guild_members:
                guild_members[gid] = []
            guild_members[gid].append(pid)
    end = time.time()
    con.close()
    return end - start

def main():
    setup_db(num_guilds=50000, num_chars=100000)

    guild_ids_large = list(range(1, 10000))
    t1 = bench_in_clause(guild_ids_large)
    print(f"Chunked 900 IN clauses: {t1:.4f}s")

    t2 = bench_single_in_clause(guild_ids_large)
    print(f"Chunked 32000 IN clauses: {t2:.4f}s")

if __name__ == "__main__":
    main()
