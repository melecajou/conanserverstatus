import os
import pytest
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timedelta

from cogs.warps import WarpsCog
import config

SERVER_NAME = "Test Server"
SERVER_CONF = {
    "NAME": SERVER_NAME,
    "ENABLED": True,
    "SERVER_IP": "127.0.0.1",
    "RCON_PORT": 25575,
    "RCON_PASS": os.getenv("RCON_PASS", "DUMMY_PASSWORD"),
    "STATUS_CHANNEL_ID": 123456789,
    "LOG_PATH": "/tmp/test.log",
    "DB_PATH": ":memory:",
    "PLAYER_DB_PATH": ":memory:",
    "WARP_CONFIG": {
        "ENABLED": True,
        "LOCATIONS": {"town": "100 100 100"},
        "HOME_ENABLED": True,
        "COOLDOWN_MINUTES": 5,
        "HOME_COOLDOWN_MINUTES": 15,
    },
}


class TestWarpsCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.wait_until_ready = AsyncMock()

        # Mock StatusCog
        self.mock_status_cog = MagicMock()
        # Mock get_player_list instead of execute_rcon
        self.mock_status_cog.get_player_list = AsyncMock(return_value=("5 | TestPlayer | A | B | steam_id", None))
        self.mock_status_cog.execute_safe_command = AsyncMock(
            return_value=("Success", None)
        )
        self.mock_status_cog.rcon_clients = {SERVER_NAME: AsyncMock()}

        self.mock_bot.get_cog.return_value = self.mock_status_cog

        # Patch config.SERVERS
        self.config_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_patcher.start()

        # Patch tasks loop to prevent autostart
        with patch("discord.ext.tasks.Loop.start"):
            self.warps_cog = WarpsCog(self.mock_bot)

        # Mock DB functions
        self.get_global_player_data_patcher = patch("cogs.warps.get_global_player_data")
        self.mock_get_global_player_data = self.get_global_player_data_patcher.start()
        self.mock_get_global_player_data.return_value = {
            "steam_id": {"discord_id": 12345}
        }

        self.get_char_coords_patcher = patch("cogs.warps.get_character_coordinates")
        self.mock_get_char_coords = self.get_char_coords_patcher.start()

        self.save_home_patcher = patch("cogs.warps.save_player_home")
        self.mock_save_home = self.save_home_patcher.start()

        self.get_home_patcher = patch("cogs.warps.get_player_home")
        self.mock_get_home = self.get_home_patcher.start()

    async def asyncTearDown(self):
        self.warps_cog.cog_unload()
        self.config_patcher.stop()
        self.get_global_player_data_patcher.stop()
        self.get_char_coords_patcher.stop()
        self.save_home_patcher.stop()
        self.get_home_patcher.stop()

    async def test_handle_warp_success(self):
        """Test processing a !warp command."""
        # Mock getting player info via StatusCog (used by WarpsCog._get_player_info)
        self.mock_status_cog.get_player_list.return_value = (
            "5 | TestPlayer | A | B | steam_id",
            None,
        )

        await self.warps_cog._handle_warp(
            "TestPlayer", "town", SERVER_CONF, SERVER_NAME
        )

        # Verify execute_safe_command was called
        self.mock_status_cog.execute_safe_command.assert_called_with(
            SERVER_NAME, "TestPlayer", ANY
        )

        # Verify call args for lambda check
        args = self.mock_status_cog.execute_safe_command.call_args
        command_template = args[0][2]
        self.assertEqual(command_template("5"), "con 5 TeleportPlayer 100 100 100")

    async def test_handle_warp_cooldown(self):
        """Test warp cooldown."""
        self.mock_status_cog.get_player_list.return_value = (
            "5 | TestPlayer | A | B | steam_id",
            None,
        )

        # First warp
        await self.warps_cog._handle_warp(
            "TestPlayer", "town", SERVER_CONF, SERVER_NAME
        )
        self.mock_status_cog.execute_safe_command.assert_called()
        self.mock_status_cog.execute_safe_command.reset_mock()

        # Second warp (immediate)
        await self.warps_cog._handle_warp(
            "TestPlayer", "town", SERVER_CONF, SERVER_NAME
        )

        # Should NOT call execute_safe_command due to cooldown
        self.mock_status_cog.execute_safe_command.assert_not_called()

    async def test_handle_home_success(self):
        """Test processing a !home command."""
        self.mock_status_cog.get_player_list.return_value = (
            "5 | TestPlayer | A | B | steam_id",
            None,
        )
        self.mock_get_home.return_value = (500, 500, 500)

        await self.warps_cog._handle_home("TestPlayer", SERVER_CONF)

        self.mock_status_cog.execute_safe_command.assert_called_with(
            SERVER_NAME, "TestPlayer", ANY
        )

        args = self.mock_status_cog.execute_safe_command.call_args
        command_template = args[0][2]
        self.assertEqual(command_template("5"), "con 5 TeleportPlayer 500 500 500")

    async def test_process_log_line(self):
        """Test log parsing triggers warp handler."""
        # Mock _handle_warp to isolate logic
        self.warps_cog._handle_warp = AsyncMock()

        log_line = "ChatWindow: Character TestPlayer (uid: 123) said: !warp town"

        await self.warps_cog._process_log_line(log_line, SERVER_CONF, SERVER_NAME)

        self.warps_cog._handle_warp.assert_called_with(
            "TestPlayer", "town", SERVER_CONF, SERVER_NAME
        )
