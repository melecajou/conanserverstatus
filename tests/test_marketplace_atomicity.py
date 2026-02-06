import pytest
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, ANY
import logging

from cogs.marketplace import MarketplaceCog

# Configuration for testing
SERVER_CONF = {
    "NAME": "Test Server",
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
    "SYNC_WAIT_SECONDS": 0
}

class TestMarketplaceAtomicity(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s # Mock translation
        self.mock_bot.wait_until_ready = AsyncMock()

        self.mock_status_cog = MagicMock()
        self.mock_status_cog.execute_safe_command = AsyncMock()
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

        self.get_balance_patcher = patch("cogs.marketplace.get_player_balance")
        self.mock_get_balance = self.get_balance_patcher.start()
        self.mock_get_balance.return_value = 1000

        self.prepare_tx_patcher = patch("cogs.marketplace.prepare_withdrawal_transaction")
        self.mock_prepare_tx = self.prepare_tx_patcher.start()

        self.complete_tx_patcher = patch("cogs.marketplace.complete_withdrawal_transaction")
        self.mock_complete_tx = self.complete_tx_patcher.start()

        self.log_action_patcher = patch("cogs.marketplace.log_market_action")
        self.mock_log_action = self.log_action_patcher.start()

        self.mock_user = MagicMock()
        self.mock_user.send = AsyncMock()
        self.mock_bot.fetch_user = AsyncMock(return_value=self.mock_user)

    async def asyncTearDown(self):
        self.market_cog.cog_unload()
        self.config_servers_patcher.stop()
        self.config_market_patcher.stop()
        self.find_discord_user_patcher.stop()
        self.get_balance_patcher.stop()
        self.prepare_tx_patcher.stop()
        self.complete_tx_patcher.stop()
        self.log_action_patcher.stop()

    async def test_withdraw_success_flow(self):
        """Test a successful withdrawal flow."""
        # Setup
        amount = 100
        tx_id = 999
        self.mock_prepare_tx.return_value = tx_id

        # Execute
        await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)

        # Verify
        # 1. Prepare called
        self.mock_prepare_tx.assert_called_with(12345, amount, "TestPlayer", "Test Server")

        # 2. RCON Executed
        self.mock_status_cog.execute_safe_command.assert_called_once()

        # 3. Complete called with COMPLETED
        self.mock_complete_tx.assert_called_with(tx_id, "COMPLETED")

        # 4. User notified success
        args, _ = self.mock_user.send.call_args
        self.assertIn("Successful", args[0])

    async def test_withdraw_rcon_failure_flow(self):
        """Test flow when RCON execution fails."""
        # Setup
        amount = 100
        tx_id = 999
        self.mock_prepare_tx.return_value = tx_id

        # Simulate RCON failure
        self.mock_status_cog.execute_safe_command.side_effect = Exception("RCON Timeout")

        # Execute
        with self.assertLogs(level='CRITICAL') as log:
            await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)
            self.assertTrue(any("CRITICAL: Withdrawal Transaction #999" in o for o in log.output))

        # Verify
        # 1. Prepare called
        self.mock_prepare_tx.assert_called()

        # 2. Complete called with ERROR_REVIEW
        self.mock_complete_tx.assert_called_with(tx_id, "ERROR_REVIEW")

        # 3. User notified pending review
        args, _ = self.mock_user.send.call_args
        self.assertIn("Pending Review", args[0])
        self.assertIn("DO NOT PANIC", args[0])

    async def test_withdraw_prepare_failure(self):
        """Test flow when preparation fails (e.g. insufficient funds race condition)."""
        # Setup
        amount = 100
        self.mock_prepare_tx.return_value = None # Failed to prepare

        # Execute
        await self.market_cog._handle_withdraw("TestPlayer", amount, SERVER_CONF)

        # Verify
        # 1. Prepare called
        self.mock_prepare_tx.assert_called()

        # 2. RCON NOT executed
        self.mock_status_cog.execute_safe_command.assert_not_called()

        # 3. Complete NOT called
        self.mock_complete_tx.assert_not_called()

        # 4. User notified cancellation
        args, _ = self.mock_user.send.call_args
        self.assertIn("Transaction cancelled", args[0])
