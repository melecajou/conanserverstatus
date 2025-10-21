import asyncio
import logging
from typing import Optional

from aiomcrcon import Client
import gettext

_ = gettext.gettext

async def attempt_rcon_connection(server_conf: dict) -> Optional[Client]:
    """Tries to connect to RCON, retrying a few times on failure."""
    rcon_client = Client(server_conf["SERVER_IP"], server_conf["RCON_PORT"], server_conf["RCON_PASS"])
    for attempt in range(3):
        try:
            await rcon_client.connect()
            logging.info(_("[{server}] RCON connection successful on attempt {attempt}/3.").format(server=server_conf['NAME'], attempt=attempt + 1))
            return rcon_client
        except Exception as e:
            logging.warning(
                _("[{server}] RCON connection attempt {attempt}/3 failed: {error}").format(
                    server=server_conf['NAME'], attempt=attempt + 1, error=e
                )
            )
            await rcon_client.close()
            if attempt < 2:
                await asyncio.sleep(attempt + 2)
    return None
