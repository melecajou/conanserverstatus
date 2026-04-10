import os
import pytest
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from cogs.marketplace import MarketplaceCog

# Configuration for testing
SERVER_CONF = {
    "NAME": "Test Server",
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
    "SYNC_WAIT_SECONDS": 0,
}


class TestMarketplaceSecurity(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s  # Mock translation
        self.mock_bot.wait_until_ready = AsyncMock()

        self.mock_status_cog = MagicMock()
        self.mock_status_cog.execute_safe_command = AsyncMock()
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

        self.get_balance_patcher = patch("cogs.marketplace.get_player_balance")
        self.mock_get_balance = self.get_balance_patcher.start()
        self.mock_get_balance.return_value = (
            1000000  # High balance to ensure check fails on limit, not funds
        )

        self.update_balance_patcher = patch("cogs.marketplace.update_player_balance")
        self.mock_update_balance = self.update_balance_patcher.start()

        self.mock_user = MagicMock()
        self.mock_user.send = AsyncMock()
        self.mock_bot.fetch_user = AsyncMock(return_value=self.mock_user)

    async def asyncTearDown(self):
        self.market_cog.cog_unload()
        self.config_servers_patcher.stop()
        self.config_market_patcher.stop()
        self.find_discord_user_patcher.stop()
        self.get_balance_patcher.stop()
        self.update_balance_patcher.stop()

    async def test_sell_exceeds_limit(self):
        """Test that selling an item with a price exceeding the limit is rejected."""
        # Limit is 65535. Try 65536.
        slot = 1
        price = 65536

        await self.market_cog._handle_sell("TestPlayer", slot, price, SERVER_CONF)

        args, _ = self.mock_user.send.call_args
        sent_msg = args[0]

        self.assertIn("Error", sent_msg)
        self.assertIn("65535", sent_msg)
        self.assertNotIn("Sell Request", sent_msg)

    async def test_sell_negative_price(self):
        """Test that selling an item with a negative price is rejected."""
        slot = 1
        price = -100

        await self.market_cog._handle_sell("TestPlayer", slot, price, SERVER_CONF)

        args, _ = self.mock_user.send.call_args
        sent_msg = args[0]

        self.assertIn("Error", sent_msg)
        self.assertIn("greater than 0", sent_msg)
        self.assertNotIn("Sell Request", sent_msg)

    async def test_withdraw_invalid_amount(self):
        """Test that withdrawing zero or negative amount is rejected with message."""
        for amount in [0, -1]:
            self.mock_user.send.reset_mock()
            await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)

            self.assertTrue(self.mock_user.send.called, f"No message sent for amount {amount}")
            args, _ = self.mock_user.send.call_args
            sent_msg = args[0]
            self.assertIn("Error", sent_msg)

    async def test_withdraw_exceeds_limit(self):
        """Test that withdrawing an amount exceeding the limit is rejected."""
        amount = 65536

        await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)

        args, _ = self.mock_user.send.call_args
        sent_msg = args[0]

        self.assertIn("Error", sent_msg)
        self.assertIn("65535", sent_msg)

        # Ensure no balance update happened
        self.mock_update_balance.assert_not_called()

    async def test_deposit_exceeds_limit(self):
        """Test that depositing an item with quantity exceeding limit is rejected."""
        slot = 1
        # We need to mock _parse_item_blob to return a large quantity
        with patch.object(self.market_cog, "_parse_item_blob") as mock_parse:
            # 1 is Quantity ID, 99999 is MARK_STAT_ID
            mock_parse.return_value = {"int": {1: 100000, 99999: 12345}, "float": {}}

            # Mock the DB query as well
            with patch("aiosqlite.connect") as mock_connect:
                mock_context = mock_connect.return_value.__aenter__.return_value
                mock_execute = MagicMock()
                mock_execute_context = MagicMock()
                mock_cursor = AsyncMock()
                mock_execute_context.__aenter__ = AsyncMock(return_value=mock_cursor)
                mock_execute_context.__aexit__ = AsyncMock(return_value=None)
                mock_execute.return_value = mock_execute_context
                mock_context.execute = mock_execute

                # First fetch for pre-check, second for verify
                mock_cursor.fetchone = AsyncMock(side_effect=[
                    (MARKET_CONFIG["CURRENCY_ITEM_ID"],),  # pre-check
                    (MARKET_CONFIG["CURRENCY_ITEM_ID"], b"dummy_blob"),  # verify
                ])

                # Mock get_char_id_by_name
                with patch(
                    "cogs.marketplace.get_char_id_by_name", return_value=1
                ):
                    # We also need to mock time.time() for the MARK_STAT_ID
                    with patch("time.time", return_value=12345):
                        await self.market_cog._handle_deposit(
                            "TestPlayer", slot, SERVER_CONF
                        )

        # _handle_deposit sends "Deposit Request" first, then error later.
        # We check the LAST call to send.
        self.assertGreaterEqual(self.mock_user.send.call_count, 2)
        args, _ = self.mock_user.send.call_args
        sent_msg = args[0]
        self.assertIn("Error", sent_msg)
        self.assertIn("65535", sent_msg)
