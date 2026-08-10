import asyncio
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import AsyncMock

import config
config.SERVERS = [{"NAME": "TestServer", "SERVER_IP": "127.0.0.1", "RCON_PORT": 25575, "RCON_PASS": "pass", "STATUS_CHANNEL_ID": 123}]
config.LANGUAGE = "en"

from cogs.status import StatusCog

async def benchmark():
    bot = AsyncMock()
    bot._ = lambda x: x

    cog = StatusCog(bot)
    cog.update_all_statuses_task.cancel()
    await cog.async_init()

    async def mock_execute(server_name, cmd, max_retries=3):
        await asyncio.sleep(0.1)
        return (f"PlayerList for {server_name}", "123")

    cog._execute_raw_rcon = AsyncMock(side_effect=mock_execute)

    start = time.time()
    tasks = [cog.get_player_list("TestServer", use_cache=True) for _ in range(100)]
    results = await asyncio.gather(*tasks)

    duration = time.time() - start
    calls = cog._execute_raw_rcon.call_count

    print(f"Concurrent calls: 100")
    print(f"Time taken: {duration:.3f}s")
    print(f"RCON calls made: {calls}")

asyncio.run(benchmark())
