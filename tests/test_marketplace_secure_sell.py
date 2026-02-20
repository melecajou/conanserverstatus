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
    "RCON_PASS": "DUMMY_PASSWORD",
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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()

def build_blob(item_template_id, int_stats=None):
    """Builds a binary blob representing item data."""
    if int_stats is None:
        int_stats = {}

    # Pack Template ID
    blob = struct.pack("<I", item_template_id)

    # Int Stats
    blob += struct.pack("<I", len(int_stats))
    for pid, pval in int_stats.items():
        blob += struct.pack("<I", pid)
        blob += struct.pack("<I", pval)

    # Float Stats (Empty)
    blob += struct.pack("<I", 0)

    return blob

class TestMarketplaceSecureSell(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.wait_until_ready = AsyncMock()

        # Mock StatusCog
        self.mock_status_cog = MagicMock()
        self.mock_status_cog.execute_safe_command = AsyncMock(return_value=("Success", None))
        self.mock_bot.get_cog.return_value = self.mock_status_cog

        # Patch config
        self.config_servers_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_servers_patcher.start()

        self.config_market_patcher = patch("config.MARKETPLACE", MARKET_CONFIG, create=True)
        self.config_market_patcher.start()

        # Patch tasks loop
        with patch("discord.ext.tasks.Loop.start"):
            self.market_cog = MarketplaceCog(self.mock_bot)

        # Mock DB functions
        self.find_discord_user_patcher = patch("cogs.marketplace.find_discord_user_by_char_name")
        self.mock_find_user = self.find_discord_user_patcher.start()
        self.mock_find_user.return_value = "12345"

        self.get_char_id_patcher = patch("cogs.marketplace.get_char_id_by_name")
        self.mock_get_char_id = self.get_char_id_patcher.start()
        self.mock_get_char_id.return_value = 1

        self.log_action_patcher = patch("cogs.marketplace.log_market_action")
        self.mock_log_action = self.log_action_patcher.start()

        # Patch aiosqlite
        self.aiosqlite_patcher = patch("aiosqlite.connect")
        self.mock_aiosqlite = self.aiosqlite_patcher.start()

        # Setup generic mock connection
        self.mock_conn = AsyncMock()
        self.mock_aiosqlite.return_value.__aenter__.return_value = self.mock_conn

        self.mock_conn.execute = MagicMock()
        self.mock_cursor = MockCursor()
        self.mock_conn.execute.return_value = self.mock_cursor

        # We need commit mock
        self.mock_conn.commit = AsyncMock()

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
        self.log_action_patcher.stop()
        self.aiosqlite_patcher.stop()

    async def test_handle_sell_success(self):
        """Test successful secure sell flow."""
        slot = 10
        price = 100
        template_id = 500
        mark_id = 99999

        # 1. First DB Read (Pre-check): Valid Item
        # 2. Second DB Read (Verify): Valid Item WITH Mark

        blob_1 = build_blob(template_id, {})
        # We don't know the exact mark value yet, but the test logic will check for *some* value at 99999
        # In the real code, we'll verify it matches the one we sent.
        # Here we simulate that the game updated the blob with the mark.
        # But wait, the code generates the mark value randomly/timestamp.
        # So we need to ensure the blob matches what the code generated?
        # Or we mock the mark generation?

        # Let's mock time.time so we know the mark value
        with patch("time.time", return_value=123456.0):
            mark_value = 123456
            blob_2 = build_blob(template_id, {mark_id: mark_value})

            # Setup DB responses
            # fetchone() is called:
            # 1. Pre-check
            # 2. Verification
            # 3. Market Listing Insert (execute returns cursor, cursor.lastrowid used)

            # The code does:
            # 1. Connect (RO) -> Execute Query -> Fetchone (Pre-check)
            # 2. RCON Mark
            # 3. Connect (RO) -> Execute Query -> Fetchone (Verify)
            # 4. Connect (RW) -> Execute Insert -> Commit

            # So side_effect should be on fetchone.
            # However, different cursors are created.
            # self.mock_cursor is reused for all execute() calls because of our setup.

            self.mock_cursor.fetchone.side_effect = [
                (template_id, blob_1),  # Pre-check
                (template_id, blob_2),  # Verify
            ]

            await self.market_cog._handle_sell("TestPlayer", slot, price, SERVER_CONF)

            # Verifications

            # 1. Check RCON Mark Command
            # Find SetInventoryItemIntStat ... 99999 ...
            mark_cmd_found = False
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd_lambda = call[0][2]
                cmd = cmd_lambda("1")
                if f"SetInventoryItemIntStat {slot} {mark_id} {mark_value} 0" in cmd:
                    mark_cmd_found = True
            self.assertTrue(mark_cmd_found, "Mark command not sent")

            # 2. Check RCON Delete Command
            delete_cmd_found = False
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd_lambda = call[0][2]
                cmd = cmd_lambda("1")
                if f"SetInventoryItemIntStat {slot} 1 0 0" in cmd:
                    delete_cmd_found = True
            self.assertTrue(delete_cmd_found, "Delete command not sent")

            # 3. Check Market Listing Insert
            # We check the arguments to execute()
            insert_called = False
            for call in self.mock_conn.execute.call_args_list:
                if "INSERT INTO market_listings" in str(call):
                    args = call[0][1] # (discord_id, template_id, dna_json, price)
                    self.assertEqual(args[1], template_id)
                    self.assertEqual(args[3], price)
                    insert_called = True
            self.assertTrue(insert_called, "Market listing not inserted")

    async def test_handle_sell_fail_swap(self):
        """Test sell failure when item is swapped (Template Mismatch)."""
        slot = 10
        price = 100
        template_id = 500
        swapped_id = 600
        mark_id = 99999

        with patch("time.time", return_value=123456.0):
            mark_value = 123456
            blob_1 = build_blob(template_id, {})
            # Blob 2 has Mark, but Wrong Template ID
            blob_2 = build_blob(swapped_id, {mark_id: mark_value})

            self.mock_cursor.fetchone.side_effect = [
                (template_id, blob_1),  # Pre-check
                (swapped_id, blob_2),   # Verify (Mismatch)
            ]

            await self.market_cog._handle_sell("TestPlayer", slot, price, SERVER_CONF)

            # Verify Delete command NOT sent
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd_lambda = call[0][2]
                cmd = cmd_lambda("1")
                if f"SetInventoryItemIntStat {slot} 1 0 0" in cmd:
                    self.fail("Delete command sent despite template mismatch")

            # Verify Insert NOT called
            for call in self.mock_conn.execute.call_args_list:
                if "INSERT INTO market_listings" in str(call):
                    self.fail("Market listing inserted despite failure")

    async def test_handle_sell_fail_no_mark(self):
        """Test sell failure when mark is missing (e.g. game didn't save or moved)."""
        slot = 10
        price = 100
        template_id = 500
        mark_id = 99999

        with patch("time.time", return_value=123456.0):
            blob_1 = build_blob(template_id, {})
            # Blob 2 has correct Template, but NO Mark
            blob_2 = build_blob(template_id, {})

            self.mock_cursor.fetchone.side_effect = [
                (template_id, blob_1),  # Pre-check
                (template_id, blob_2),  # Verify (Missing Mark)
            ]

            await self.market_cog._handle_sell("TestPlayer", slot, price, SERVER_CONF)

            # Verify Delete command NOT sent
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd_lambda = call[0][2]
                cmd = cmd_lambda("1")
                if f"SetInventoryItemIntStat {slot} 1 0 0" in cmd:
                    self.fail("Delete command sent despite missing mark")

    async def test_handle_sell_fail_empty_slot(self):
        """Test sell failure when slot becomes empty."""
        slot = 10
        price = 100
        template_id = 500

        with patch("time.time", return_value=123456.0):
            blob_1 = build_blob(template_id, {})

            self.mock_cursor.fetchone.side_effect = [
                (template_id, blob_1),  # Pre-check
                None,                   # Verify (Empty Slot)
            ]

            await self.market_cog._handle_sell("TestPlayer", slot, price, SERVER_CONF)

            # Verify Delete command NOT sent
            for call in self.mock_status_cog.execute_safe_command.call_args_list:
                cmd_lambda = call[0][2]
                cmd = cmd_lambda("1")
                if f"SetInventoryItemIntStat {slot} 1 0 0" in cmd:
                    self.fail("Delete command sent despite empty slot")
