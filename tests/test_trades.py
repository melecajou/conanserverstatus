import pytest
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from cogs.trades import TradesCog
import config

SERVER_NAME = "Test Server"
SERVER_CONF = {
    "NAME": SERVER_NAME,
    "ENABLED": True,
    "SERVER_IP": "127.0.0.1",
    "RCON_PORT": 25575,
    "RCON_PASS": "password",
    "STATUS_CHANNEL_ID": 123456789,
    "LOG_PATH": "/tmp/test.log",
    "DB_PATH": ":memory:",
}

TRADE_CONFIG = {
    "sword": {
        "label": "Mighty Sword",
        "price_id": 100,
        "price_amount": 10,
        "item_id": 200,
        "quantity": 1
    }
}

class TestTradesCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.wait_until_ready = AsyncMock()

        # Mock StatusCog
        self.mock_status_cog = MagicMock()
        self.mock_status_cog.execute_rcon = AsyncMock(return_value=("Success", None))
        self.mock_status_cog.execute_safe_command = AsyncMock(return_value=("Success", None))
        self.mock_status_cog.rcon_clients = {SERVER_NAME: AsyncMock()}

        self.mock_bot.get_cog.return_value = self.mock_status_cog

        # Patch config.SERVERS and TRADE_ITEMS
        self.config_servers_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_servers_patcher.start()

        self.config_trades_patcher = patch("config.TRADE_ITEMS", TRADE_CONFIG, create=True)
        self.config_trades_patcher.start()

        # Patch tasks loop
        with patch("discord.ext.tasks.Loop.start"):
            self.trades_cog = TradesCog(self.mock_bot)

        # Mock DB functions
        self.find_discord_user_patcher = patch("cogs.trades.find_discord_user_by_char_name")
        self.mock_find_discord_user = self.find_discord_user_patcher.start()
        self.mock_find_discord_user.return_value = "12345"

        self.get_char_id_patcher = patch("cogs.trades.get_char_id_by_name")
        self.mock_get_char_id = self.get_char_id_patcher.start()
        self.mock_get_char_id.return_value = 1

        self.get_backpack_patcher = patch("cogs.trades.get_item_in_backpack")
        self.mock_get_backpack = self.get_backpack_patcher.start()

        # Mock fetch_user
        self.mock_user = MagicMock()
        self.mock_user.send = AsyncMock()
        self.mock_bot.fetch_user = AsyncMock(return_value=self.mock_user)

    async def asyncTearDown(self):
        self.trades_cog.cog_unload()
        self.config_servers_patcher.stop()
        self.config_trades_patcher.stop()
        self.find_discord_user_patcher.stop()
        self.get_char_id_patcher.stop()
        self.get_backpack_patcher.stop()

    async def test_handle_buy_success(self):
        """Test successful purchase."""
        # Setup: Enough funds
        self.mock_get_backpack.return_value = {"quantity": 20, "slot": 5}
        # Mock ListPlayers response for execute_rcon check (if any manual check remains)
        self.mock_status_cog.execute_rcon.return_value = ("5 | TestPlayer | A | B | steam_id", None)

        await self.trades_cog._handle_buy("TestPlayer", "sword", SERVER_CONF)

        # Verify safe command execution
        # Should be called twice: Deduct and Spawn
        self.assertEqual(self.mock_status_cog.execute_safe_command.call_count, 2)

        # Verify first call (Deduct)
        args1 = self.mock_status_cog.execute_safe_command.call_args_list[0]
        # args1[0] is (server_name, char_name, lambda)
        self.assertEqual(args1[0][0], SERVER_NAME)
        self.assertEqual(args1[0][1], "TestPlayer")
        # Check command
        cmd1 = args1[0][2]("5")
        # Deduct 10 from 20 -> 10 remaining
        self.assertIn("SetInventoryItemIntStat 5 1 10 0", cmd1)

        # Verify second call (Spawn)
        args2 = self.mock_status_cog.execute_safe_command.call_args_list[1]
        cmd2 = args2[0][2]("5")
        # Spawn item 200 quantity 1
        self.assertIn("SpawnItem 200 1", cmd2)

        # Verify success DM
        self.mock_user.send.assert_called()
        self.assertIn("Purchase complete", str(self.mock_user.send.call_args_list[-1]))

    async def test_handle_buy_insufficient_funds(self):
        """Test purchase failure due to insufficient funds."""
        self.mock_get_backpack.return_value = {"quantity": 5, "slot": 5} # Needs 10

        await self.trades_cog._handle_buy("TestPlayer", "sword", SERVER_CONF)

        self.mock_status_cog.execute_safe_command.assert_not_called()
        self.mock_user.send.assert_called()
        self.assertIn("Insufficient funds", str(self.mock_user.send.call_args_list[-1]))

    async def test_process_log_line(self):
        """Test log line parsing for trade."""
        self.trades_cog._handle_buy = AsyncMock()

        line = "ChatWindow: Character TestPlayer (uid: 123) said: !buy sword"
        await self.trades_cog._process_log_line(line, SERVER_CONF)

        self.trades_cog._handle_buy.assert_called_with("TestPlayer", "sword", SERVER_CONF)
