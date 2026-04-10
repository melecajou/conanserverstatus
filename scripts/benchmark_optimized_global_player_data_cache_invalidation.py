import time
import random
import sys
import os

# Add parent directory to path so we can import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import utils.database

# Setup test cache
CACHE_SIZE = 100000
GLOBAL_DB_PATH = "data/global_registry.db"

_DISCORD_TO_PLATFORM_CACHE = {}

def setup_cache():
    utils.database._GLOBAL_PLAYER_CACHE.clear()
    _DISCORD_TO_PLATFORM_CACHE.clear()
    for i in range(CACHE_SIZE):
        platform_id = f"steam_{i}"
        discord_id = i % 1000  # 1000 unique discord users

        cache_key = (platform_id, GLOBAL_DB_PATH)
        utils.database._GLOBAL_PLAYER_CACHE[cache_key] = {
            "data": {
                "discord_id": discord_id,
                "vip_level": 1,
                "vip_expiry": None
            },
            "timestamp": time.time()
        }

        index_key = (discord_id, GLOBAL_DB_PATH)
        if index_key not in _DISCORD_TO_PLATFORM_CACHE:
            _DISCORD_TO_PLATFORM_CACHE[index_key] = set()
        _DISCORD_TO_PLATFORM_CACHE[index_key].add(platform_id)

def measure_invalidation(discord_id_to_invalidate):
    start_time = time.time()

    # Invalidate using secondary index
    index_key = (discord_id_to_invalidate, GLOBAL_DB_PATH)
    platform_ids = _DISCORD_TO_PLATFORM_CACHE.get(index_key, set())

    deleted = 0
    for pid in list(platform_ids):
        cache_key = (pid, GLOBAL_DB_PATH)
        if cache_key in utils.database._GLOBAL_PLAYER_CACHE:
            del utils.database._GLOBAL_PLAYER_CACHE[cache_key]
            deleted += 1

    if index_key in _DISCORD_TO_PLATFORM_CACHE:
        del _DISCORD_TO_PLATFORM_CACHE[index_key]

    end_time = time.time()
    return end_time - start_time, deleted

if __name__ == "__main__":
    print("Setting up cache...")
    setup_cache()

    print("Measuring invalidation time...")
    total_time = 0
    num_runs = 50
    deleted_total = 0

    for i in range(num_runs):
        discord_id = random.randint(0, 999)
        t, deleted = measure_invalidation(discord_id)
        total_time += t
        deleted_total += deleted

        # Restore what we deleted so size stays constant
        for j in range(deleted):
            platform_id = f"steam_restored_{i}_{j}"

            cache_key = (platform_id, GLOBAL_DB_PATH)
            utils.database._GLOBAL_PLAYER_CACHE[cache_key] = {
                "data": {
                    "discord_id": discord_id,
                    "vip_level": 1,
                    "vip_expiry": None
                },
                "timestamp": time.time()
            }

            index_key = (discord_id, GLOBAL_DB_PATH)
            if index_key not in _DISCORD_TO_PLATFORM_CACHE:
                _DISCORD_TO_PLATFORM_CACHE[index_key] = set()
            _DISCORD_TO_PLATFORM_CACHE[index_key].add(platform_id)

    avg_time = total_time / num_runs
    print(f"Average time per invalidation: {avg_time:.8f} seconds")
    print(f"Average items deleted per invalidation: {deleted_total / num_runs:.1f}")
