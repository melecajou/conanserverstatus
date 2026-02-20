import os
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
    "RCON_PASS": os.getenv("RCON_PASS", "DUMMY_PASSWORD"),
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

        self.prepare_tx_patcher = patch(
            "cogs.marketplace.prepare_withdrawal_transaction"
        )
        self.mock_prepare_tx = self.prepare_tx_patcher.start()
        self.mock_prepare_tx.return_value = 777

        self.complete_tx_patcher = patch(
            "cogs.marketplace.complete_withdrawal_transaction"
        )
        self.mock_complete_tx = self.complete_tx_patcher.start()

        self.log_action_patcher = patch("cogs.marketplace.log_market_action")
        self.mock_log_action = self.log_action_patcher.start()

        self.exec_purchase_patcher = patch("cogs.marketplace.execute_marketplace_purchase")
        self.mock_exec_purchase = self.exec_purchase_patcher.start()

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
        self.prepare_tx_patcher.stop()
        self.complete_tx_patcher.stop()
        self.log_action_patcher.stop()
        self.exec_purchase_patcher.stop()
        self.aiosqlite_patcher.stop()

    async def test_handle_withdraw_success(self):
        """Test successful withdrawal."""
        amount = 100
        await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)

        self.mock_prepare_tx.assert_called_with(12345, 100, "TestPlayer", "Test Server")
        self.mock_status_cog.execute_safe_command.assert_called_with(
            SERVER_NAME, "TestPlayer", ANY
        )
        cmd = self.mock_status_cog.execute_safe_command.call_args[0][2]("5")
        # Spawn 999 (Currency) Amount 100
        self.assertIn("SpawnItem 999 100", cmd)
        self.mock_complete_tx.assert_called_with(777, "COMPLETED")

    async def test_handle_deposit_success(self):
        """Test successful deposit."""
        slot = 5

        def build_blob(item_template_id, int_stats=None):
            if int_stats is None:
                int_stats = {}
            blob = struct.pack("<I", item_template_id)
            blob += struct.pack("<I", len(int_stats))
            for pid, pval in int_stats.items():
                blob += struct.pack("<I", pid)
                blob += struct.pack("<I", pval)
            blob += struct.pack("<I", 0)
            return blob

        template_id = 999
        blob_1 = build_blob(template_id, {})

        with patch("time.time", return_value=123456.0):
            mark_value = 123456
            blob_2 = build_blob(template_id, {99999: mark_value, 1: 1}) # 1 is Quantity

            self.mock_cursor.fetchone.side_effect = [
                (template_id, blob_1),
                (template_id, blob_2),
            ]

            await self.market_cog._handle_deposit("TestPlayer", slot, SERVER_CONF)

            # 1. Check Mark Command
            mark_found = False
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd = call[0][2]("5")
                if "SetInventoryItemIntStat 5 99999 123456 0" in cmd:
                    mark_found = True
            self.assertTrue(mark_found, "Mark command not found")

            # 2. Check Delete Command
            delete_found = False
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd = call[0][2]("5")
                if "SetInventoryItemIntStat 5 1 0 0" in cmd:
                    delete_found = True
            self.assertTrue(delete_found, "Delete command not found")

            # 3. Update Balance
            self.mock_update_balance.assert_called_with(
                12345, 1
            )

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

        # Mock successful purchase transaction
        self.mock_exec_purchase.return_value = (listing, None)

        await self.market_cog._handle_buy("TestPlayer", listing_id, SERVER_CONF)

        # Verifications

        # 1. Purchase Executed
        self.mock_exec_purchase.assert_called_with(12345, listing_id)

        # 2. Spawn Command (Single Call)
        # Check that SpawnItem was called via execute_safe_command
        # We need to find the call that has SpawnItem
        spawn_found = False
        for call in self.mock_status_cog.execute_safe_command.call_args_list:
            cmd_lambda = call[0][2]
            cmd = cmd_lambda("5")
            if "SpawnItem 500 1" in cmd:
                spawn_found = True
                break
        self.assertTrue(spawn_found, "Spawn command not sent via execute_safe_command")

        # 3. DNA Injection (Batch Call)
        self.mock_status_cog.execute_safe_batch.assert_called()
        # Verify templates in batch
        batch_args = self.mock_status_cog.execute_safe_batch.call_args
        self.assertEqual(batch_args[0][0], SERVER_NAME)
        self.assertEqual(batch_args[0][1], "TestPlayer")
        templates = batch_args[0][2]

        int_found = False
        float_found = False
        for tmpl in templates:
            cmd = tmpl("5")
            if "SetInventoryItemIntStat 100 10 50 0" in cmd:
                int_found = True
            if "SetInventoryItemFloatStat 100 20 1.5 0" in cmd:
                float_found = True

        self.assertTrue(int_found, "DNA Int injection not in batch")
        self.assertTrue(float_found, "DNA Float injection not in batch")
