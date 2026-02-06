import pytest
import asyncio
import json
import struct
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from cogs.marketplace import MarketplaceCog
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

MARKET_CONFIG = {
    "ENABLED": True,
    "CURRENCY_ITEM_ID": 999,
    "CURRENCY_NAME": "Coins",
    "SYNC_WAIT_SECONDS": 0,  # Speed up tests
}


# Helper class for aiosqlite Cursor mocking
class MockCursor:
    def __init__(self, *args, **kwargs):
        self.fetchone = AsyncMock()
        self.fetchall = AsyncMock()
        self.lastrowid = 1
        # MagicMock compatibility for checks if needed, or simple pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __await__(self):
        async def _ret():
            return self

        return _ret().__await__()


class TestMarketplaceCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.wait_until_ready = AsyncMock()

        # Mock StatusCog
        self.mock_status_cog = MagicMock()
        self.mock_status_cog.execute_rcon = AsyncMock(return_value=("Success", None))
        self.mock_status_cog.execute_safe_command = AsyncMock(
            return_value=("Success", None)
        )

        self.mock_bot.get_cog.return_value = self.mock_status_cog

        # Patch config
        self.config_servers_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_servers_patcher.start()

        self.config_market_patcher = patch(
            "config.MARKETPLACE", MARKET_CONFIG, create=True
        )
        self.config_market_patcher.start()

        # Patch tasks loop
        with patch("discord.ext.tasks.Loop.start"):
            self.market_cog = MarketplaceCog(self.mock_bot)

        # Mock DB functions
        self.find_discord_user_patcher = patch(
            "cogs.marketplace.find_discord_user_by_char_name"
        )
        self.mock_find_user = self.find_discord_user_patcher.start()
        self.mock_find_user.return_value = "12345"

        self.get_char_id_patcher = patch("cogs.marketplace.get_char_id_by_name")
        self.mock_get_char_id = self.get_char_id_patcher.start()
        self.mock_get_char_id.return_value = 1

        self.get_balance_patcher = patch("cogs.marketplace.get_player_balance")
        self.mock_get_balance = self.get_balance_patcher.start()
        self.mock_get_balance.return_value = 1000

        self.update_balance_patcher = patch("cogs.marketplace.update_player_balance")
        self.mock_update_balance = self.update_balance_patcher.start()
        self.mock_update_balance.return_value = True

        self.log_action_patcher = patch("cogs.marketplace.log_market_action")
        self.mock_log_action = self.log_action_patcher.start()

        # Patch aiosqlite
        self.aiosqlite_patcher = patch("aiosqlite.connect")
        self.mock_aiosqlite = self.aiosqlite_patcher.start()

        # Setup generic mock connection
        self.mock_conn = AsyncMock()  # Connection is an async context manager
        self.mock_aiosqlite.return_value.__aenter__.return_value = self.mock_conn

        # Override execute to be MagicMock, not AsyncMock
        self.mock_conn.execute = MagicMock()
        self.mock_cursor = MockCursor()
        self.mock_conn.execute.return_value = self.mock_cursor

        # Mock fetch_user
        self.mock_user = MagicMock()
        self.mock_user.send = AsyncMock()
        self.mock_bot.fetch_user = AsyncMock(return_value=self.mock_user)

    async def asyncTearDown(self):
        self.market_cog.cog_unload()
        self.config_servers_patcher.stop()
        self.config_market_patcher.stop()
        self.find_discord_user_patcher.stop()
        self.get_char_id_patcher.stop()
        self.get_balance_patcher.stop()
        self.update_balance_patcher.stop()
        self.log_action_patcher.stop()
        self.aiosqlite_patcher.stop()

    async def test_handle_withdraw_success(self):
        """Test successful withdrawal."""
        amount = 100
        await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)

        self.mock_update_balance.assert_called_with(12345, -100)
        self.mock_status_cog.execute_safe_command.assert_called_with(
            SERVER_NAME, "TestPlayer", ANY
        )
        cmd = self.mock_status_cog.execute_safe_command.call_args[0][2]("5")
        # Spawn 999 (Currency) Amount 100
        self.assertIn("SpawnItem 999 100", cmd)

    async def test_handle_deposit_success(self):
        """Test successful deposit."""
        slot = 5

        # Setup cursor response
        # We need a fresh cursor for this test? self.mock_cursor is shared.
        self.mock_cursor.fetchone.return_value = (999, None)

        await self.market_cog._handle_deposit("TestPlayer", slot, SERVER_CONF)

        # 1. Delete item via Safe Command
        self.mock_status_cog.execute_safe_command.assert_called_with(
            SERVER_NAME, "TestPlayer", ANY
        )
        cmd = self.mock_status_cog.execute_safe_command.call_args[0][2]("5")
        # Set quantity to 0
        self.assertIn("SetInventoryItemIntStat 5 1 0 0", cmd)

        # 2. Update Balance
        self.mock_update_balance.assert_called_with(
            12345, 1
        )  # Default quantity 1 if no blob

    async def test_handle_buy_success(self):
        """Test successful buy with DNA injection."""
        listing_id = 1

        # listing: id, seller_id, template_id, dna, price, status
        dna = {"int": {10: 50}, "float": {20: 1.5}}
        listing = {
            "id": 1,
            "seller_discord_id": 67890,
            "item_template_id": 500,
            "item_dna": json.dumps(dna),
            "price": 500,
            "status": "active",
        }

        # --- Configure Mock Connections ---
        # We need separate cursors/responses for global vs local DB calls.

        # MockCursor instances
        global_cursor = MockCursor()
        server_cursor = MockCursor()

        # Mock Connections
        mock_global_conn = AsyncMock()
        mock_global_conn.execute = MagicMock(return_value=global_cursor)

        mock_server_conn = AsyncMock()
        mock_server_conn.execute = MagicMock(return_value=server_cursor)

        # Side effect to return different connections based on DB Path
        def connect_side_effect(*args, **kwargs):
            path = str(args[0])
            mock_ctx = AsyncMock()
            if "global_registry.db" in path or "GLOBAL_DB_PATH" in path:
                mock_ctx.__aenter__.return_value = mock_global_conn
            else:
                mock_ctx.__aenter__.return_value = mock_server_conn
            return mock_ctx

        self.mock_aiosqlite.side_effect = connect_side_effect

        # --- Global DB Setup ---
        global_cursor.fetchone.return_value = listing

        # --- Server DB Setup ---
        server_cursor.fetchone.side_effect = [None]  # Stacking check
        server_cursor.fetchall.side_effect = [[], [(100, 0, 500)]]  # Before  # After

        await self.market_cog._handle_buy("TestPlayer", listing_id, SERVER_CONF)

        # Verifications

        # 1. Balance Updated
        self.mock_update_balance.assert_any_call(12345, -500)  # Buyer
        self.mock_update_balance.assert_any_call(67890, 500)  # Seller

        calls = self.mock_status_cog.execute_safe_command.call_args_list
        spawn_found = False
        int_found = False
        float_found = False

        for call in calls:
            cmd_lambda = call[0][2]
            cmd = cmd_lambda("5")
            if "SpawnItem 500 1" in cmd:
                spawn_found = True
            if "SetInventoryItemIntStat 100 10 50 0" in cmd:
                int_found = True
            if "SetInventoryItemFloatStat 100 20 1.5 0" in cmd:
                float_found = True

        self.assertTrue(spawn_found, "Spawn command not sent")
        self.assertTrue(int_found, "DNA Int injection not sent")
        self.assertTrue(float_found, "DNA Float injection not sent")
