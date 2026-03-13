import time
import sqlite3
import os
import sys
import unittest

# Add the parent directory to sys.path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import find_discord_user_by_char_name, _USER_CACHE

GAME_DB_PATH = "test_finduser_logic_game.db"
GLOBAL_DB_PATH = "test_finduser_logic_global.db"

class TestFindUserCaching(unittest.TestCase):
    def setUp(self):
        if os.path.exists(GAME_DB_PATH):
            os.remove(GAME_DB_PATH)
        if os.path.exists(GLOBAL_DB_PATH):
            os.remove(GLOBAL_DB_PATH)
        _USER_CACHE.clear()

        # Setup Game DB
        with sqlite3.connect(GAME_DB_PATH) as con:
            cur = con.cursor()
            cur.execute("CREATE TABLE characters (id INTEGER PRIMARY KEY, char_name TEXT, playerId TEXT, guild INTEGER)")
            cur.execute("CREATE TABLE account (id TEXT PRIMARY KEY, platformId TEXT, user TEXT)")
            cur.execute("INSERT INTO characters (char_name, playerId) VALUES (?, ?)", ("TestChar", "PID_1"))
            cur.execute("INSERT INTO account (id, platformId) VALUES (?, ?)", ("PID_1", "Steam_1"))
            con.commit()

        # Setup Global DB
        with sqlite3.connect(GLOBAL_DB_PATH) as con:
            cur = con.cursor()
            cur.execute("CREATE TABLE user_identities (platform_id TEXT PRIMARY KEY, discord_id INTEGER NOT NULL)")
            cur.execute("INSERT INTO user_identities (platform_id, discord_id) VALUES (?, ?)", ("Steam_1", 12345))
            con.commit()

    def tearDown(self):
        if os.path.exists(GAME_DB_PATH):
            os.remove(GAME_DB_PATH)
        if os.path.exists(GLOBAL_DB_PATH):
            os.remove(GLOBAL_DB_PATH)
        _USER_CACHE.clear()

    def test_cache_hit(self):
        # First call should populate cache
        res1 = find_discord_user_by_char_name(GAME_DB_PATH, "TestChar", GLOBAL_DB_PATH)
        self.assertEqual(res1, 12345)

        # Modify DB directly to see if it still returns cached value
        with sqlite3.connect(GLOBAL_DB_PATH) as con:
            cur = con.cursor()
            cur.execute("UPDATE user_identities SET discord_id = 99999 WHERE platform_id = 'Steam_1'")
            con.commit()

        # Second call should return cached value (12345), not 99999
        res2 = find_discord_user_by_char_name(GAME_DB_PATH, "TestChar", GLOBAL_DB_PATH)
        self.assertEqual(res2, 12345)

    def test_cache_expiration(self):
        # First call should populate cache
        res1 = find_discord_user_by_char_name(GAME_DB_PATH, "TestChar", GLOBAL_DB_PATH)
        self.assertEqual(res1, 12345)

        # Manually expire the cache entry
        cache_key = (GAME_DB_PATH, "TestChar", GLOBAL_DB_PATH)
        _USER_CACHE[cache_key]["timestamp"] -= 600 # 10 mins ago

        # Modify DB
        with sqlite3.connect(GLOBAL_DB_PATH) as con:
            cur = con.cursor()
            cur.execute("UPDATE user_identities SET discord_id = 99999 WHERE platform_id = 'Steam_1'")
            con.commit()

        # Second call should return new value (99999)
        res2 = find_discord_user_by_char_name(GAME_DB_PATH, "TestChar", GLOBAL_DB_PATH)
        self.assertEqual(res2, 99999)

    def test_partial_match(self):
        # find_discord_user_by_char_name uses LIKE %char_name%
        res = find_discord_user_by_char_name(GAME_DB_PATH, "estCha", GLOBAL_DB_PATH)
        self.assertEqual(res, 12345)

        cache_key = (GAME_DB_PATH, "estCha", GLOBAL_DB_PATH)
        self.assertIn(cache_key, _USER_CACHE)

if __name__ == "__main__":
    unittest.main()
