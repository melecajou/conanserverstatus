import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

async def benchmark():
    bot = MagicMock()

    # Mock for get_user (fast cache)
    cached_user = MagicMock()
    bot.get_user.return_value = cached_user

    # Mock for fetch_user (slow API)
    api_user = MagicMock()
    async def mock_fetch_user(user_id):
        await asyncio.sleep(0.05) # Simulate API latency (50ms)
        return api_user

    bot.fetch_user = mock_fetch_user

    discord_id = 123456789

    # Baseline: fetch_user always
    start_time = time.perf_counter()
    for _ in range(100):
        user = await bot.fetch_user(discord_id)
    baseline_time = time.perf_counter() - start_time

    # Optimized: get_user first
    start_time = time.perf_counter()
    for _ in range(100):
        user = bot.get_user(discord_id) or await bot.fetch_user(discord_id)
    optimized_time = time.perf_counter() - start_time

    print(f"Baseline Time (fetch_user only): {baseline_time:.4f}s")
    print(f"Optimized Time (get_user + fetch_user fallback): {optimized_time:.4f}s")
    print(f"Improvement: {baseline_time / optimized_time:.2f}x faster")

if __name__ == "__main__":
    asyncio.run(benchmark())
