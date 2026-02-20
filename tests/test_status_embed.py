import os
import pytest
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.status import StatusCog
import config

SERVER_CONF = {
    "NAME": "Test Server",
    "ALIAS": "Test",
    "ENABLED": True,
    "SERVER_IP": "127.0.0.1",
    "RCON_PORT": 25575,
    "RCON_PASS": os.getenv("RCON_PASS", "DUMMY_PASSWORD"),
    "STATUS_CHANNEL_ID": 123456789,
    "LOG_PATH": None,
    "DB_PATH": ":memory:",
    "PLAYER_DB_PATH": ":memory:",
}


class TestStatusEmbed(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.get_channel = MagicMock()
        self.mock_bot.wait_until_ready = AsyncMock()
        self.mock_bot.change_presence = AsyncMock()
        self.mock_bot.dispatch = MagicMock()

        # Patch config.SERVERS
        self.config_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_patcher.start()

        # Patch tasks loop
        with patch("discord.ext.tasks.Loop.start"):
            self.status_cog = StatusCog(self.mock_bot)

    async def asyncTearDown(self):
        self.status_cog.update_all_statuses_task.cancel()
        self.config_patcher.stop()

    async def test_get_server_status_embed_online(self):
        """Test _get_server_status_embed with online players."""

        # Mock _get_player_lines
        self.status_cog._get_player_lines = AsyncMock(
            return_value=["0 | Player1 | X | Y | Pid1"]
        )

        # Mock database calls
        # Note: Since we use asyncio.to_thread(func, ...), we patch 'cogs.status.func'
        # The mock will be called by to_thread.

        levels_mock = MagicMock(return_value={"Player1": 60})
        player_data_mock = MagicMock(
            return_value={"Pid1": {"online_minutes": 120, "is_registered": True}}
        )
        global_data_mock = MagicMock(return_value={"Pid1": {"discord_id": 12345}})

        with patch("cogs.status.get_batch_player_levels", levels_mock), patch(
            "cogs.status.get_batch_player_data", player_data_mock
        ), patch("cogs.status.get_global_player_data", global_data_mock):

            rcon_client = MagicMock()
            embed, count, server_data = await self.status_cog._get_server_status_embed(
                SERVER_CONF, rcon_client
            )

            # Assertions
            self.assertEqual(count, 1)
            self.assertEqual(server_data["name"], "Test Server")
            self.assertEqual(len(server_data["online_players"]), 1)
            self.assertEqual(server_data["levels_map"]["Player1"], 60)

            # Check Embed content
            self.assertIn("Player1", embed.fields[0].value)
            self.assertIn("(60)", embed.fields[0].value)  # Level
            self.assertIn("2h 0m", embed.fields[0].value)  # Playtime

    async def test_get_server_status_embed_offline(self):
        """Test _get_server_status_embed when server is offline."""
        self.status_cog._get_player_lines = AsyncMock(return_value=None)

        rcon_client = MagicMock()
        embed, count, server_data = await self.status_cog._get_server_status_embed(
            SERVER_CONF, rcon_client
        )

        self.assertEqual(count, 0)
        self.assertIsNone(server_data)
        self.assertIn("Could not connect", embed.description)
