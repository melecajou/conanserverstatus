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
    cog.COMMAND_COOLDOWN = 0

    async def mock_execute(server_name, cmd, max_retries=3):
        await asyncio.sleep(0.01)
        if cmd == "ListPlayers":
            return ("1|Player1|...|...|...", "123")
        return ("Success", "123")

    cog._execute_raw_rcon = AsyncMock(side_effect=mock_execute)

    start = time.time()
    await cog.execute_safe_batch("TestServer", "Player1", [lambda idx: f"GiveItem {idx} 123 1", lambda idx: f"GiveItem {idx} 456 1"])
    duration = time.time() - start

    calls = cog._execute_raw_rcon.call_count
    list_player_calls = sum(1 for call in cog._execute_raw_rcon.call_args_list if call[0][1] == "ListPlayers")

    print(f"Time taken: {duration:.3f}s")
    print(f"RCON calls made: {calls} (ListPlayers: {list_player_calls})")

asyncio.run(benchmark())
