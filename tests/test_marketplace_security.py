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

        # Verify error message sent
        # We verify that a message containing "Price must be" or similar is sent.
        # Since we haven't implemented the specific message yet, we look for a rejection.
        # But more importantly, we assert that NO DB/Market action was taken.

        # In _handle_sell, if it proceeds, it sends "Sell Request: Listing item..."
        # If rejected, it should send error.

        # We assert that "Sell Request" was NOT sent.
        args, _ = self.mock_user.send.call_args
        sent_msg = args[0]

        # Currently, without the fix, this test would likely proceed (or fail later in logic).
        # We want to assert that we catch it early.

        # If fix is implemented, we expect a specific error.
        # For TDD, I expect this test to fail (it will likely proceed to try to sell).

        # Let's check if update_player_balance was NOT called (sell doesn't update balance immediately, but it does other things).
        # _handle_sell does: 1. check price<=0. 2. send "Sell Request". 3. wait. 4. DB read. 5. RCON remove. 6. DB insert.

        # If validation passes (which it currently does for high numbers), it will try to send "Sell Request".
        # So we can assert that "Sell Request" is NOT in the message if we assume the fix prevents it.
        # But since we are WRITING the test first, we want it to FAIL if the fix is not there.
        # Without the fix, "Sell Request" IS sent.
        # So assertions:
        # 1. Message sent contains "Error" (which it won't currently)
        # OR
        # 2. We assert we get the error message we PLAN to add.

        # Let's Assert that the user is told about the limit.
        self.assertIn("Error", sent_msg)
        self.assertIn("65535", sent_msg)  # Expecting the limit to be mentioned

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
