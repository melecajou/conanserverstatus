import os

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import aiosqlite

# Start of test file
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

class TestMarketplaceConcurrency(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot._ = lambda s: s
        self.bot.fetch_user = AsyncMock()
        self.user = MagicMock()
        self.user.send = AsyncMock()
        self.bot.fetch_user.return_value = self.user

        # Patch config
        self.config_servers_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_servers_patcher.start()

        self.config_market_patcher = patch("config.MARKETPLACE", {
            'ENABLED': True,
            'CURRENCY_ITEM_ID': 999,
            'CURRENCY_NAME': 'Coins',
            'SYNC_WAIT_SECONDS': 0.01
        }, create=True)
        self.config_market_patcher.start()

        # Patch DB functions
        self.get_char_id_patcher = patch("cogs.marketplace.get_char_id_by_name", return_value=123)
        self.get_char_id_patcher.start()

        self.find_user_patcher = patch("cogs.marketplace.find_discord_user_by_char_name", return_value=456)
        self.find_user_patcher.start()

        self.get_balance_patcher = patch("cogs.marketplace.get_player_balance", return_value=1000)
        self.get_balance_patcher.start()

        self.update_balance_patcher = patch("cogs.marketplace.update_player_balance", return_value=True)
        self.update_balance_patcher.start()

        self.log_action_patcher = patch("cogs.marketplace.log_market_action")
        self.log_action_patcher.start()

        # Patch LogWatcher
        self.log_watcher_patcher = patch("cogs.marketplace.LogWatcher")
        self.mock_log_watcher = self.log_watcher_patcher.start()
        self.mock_log_watcher.return_value.read_new_lines = AsyncMock(return_value=[])

        # Patch aiosqlite.connect
        self.connect_patcher = patch('aiosqlite.connect')
        self.mock_connect = self.connect_patcher.start()

        # Setup DB mocks
        self.mock_db = MagicMock()
        self.mock_db.commit = AsyncMock()
        self.mock_connect.return_value.__aenter__.return_value = self.mock_db

        self.mock_cursor = AsyncMock()
        self.mock_cursor.lastrowid = 1

        # Simulate Inventory State
        self.item_in_slot = True
        self.marked = False

        async def fetchone_side_effect():
            if not self.item_in_slot:
                return None
            if self.marked:
                return (1001, b'MARKED_BLOB')
            return (1001, b'')

        self.mock_cursor.fetchone.side_effect = fetchone_side_effect

        # Create a helper object that is both awaitable and an async context manager
        class AsyncContextAwaitable:
            def __init__(self, cursor):
                self.cursor = cursor

            def __await__(self):
                async def _get_cursor():
                    return self.cursor
                return _get_cursor().__await__()

            async def __aenter__(self):
                return self.cursor

            async def __aexit__(self, exc_type, exc, tb):
                pass

        self.mock_db.execute.side_effect = lambda *args, **kwargs: AsyncContextAwaitable(self.mock_cursor)

        # Patch time.time for consistent mark value
        self.time_patcher = patch("time.time", return_value=123456.0)
        self.time_patcher.start()

        # Patch tasks loop
        with patch("discord.ext.tasks.Loop.start"):
            self.cog = MarketplaceCog(self.bot)

        # Patch _parse_item_blob on the instance (or class)
        # We can just override the method on the instance since we created it
        self.original_parse = self.cog._parse_item_blob
        def mock_parse(tid, blob):
            if blob == b'MARKED_BLOB':
                return {'int': {99999: 123456}, 'float': {}}
            return {'int': {}, 'float': {}}
        self.cog._parse_item_blob = mock_parse

        self.status_cog = MagicMock()
        self.status_cog.execute_safe_command = AsyncMock()

        # When RCON remove command is called, we update state
        async def execute_rcon(server, char, cmd_gen):
            cmd = cmd_gen("1")
            if "99999" in cmd: # Mark command
                 self.marked = True
            if "SetInventoryItemIntStat" in cmd and " 1 0 0" in cmd: # Delete command
                self.item_in_slot = False
            return "OK"

        self.status_cog.execute_safe_command.side_effect = execute_rcon
        self.bot.get_cog.return_value = self.status_cog

    async def asyncTearDown(self):
        self.connect_patcher.stop()
        self.config_servers_patcher.stop()
        self.config_market_patcher.stop()
        self.get_char_id_patcher.stop()
        self.find_user_patcher.stop()
        self.get_balance_patcher.stop()
        self.update_balance_patcher.stop()
        self.log_action_patcher.stop()
        self.log_watcher_patcher.stop()
        self.time_patcher.stop()
        self.cog.cog_unload()

    async def test_race_condition_sell(self):
        """Test that concurrent sell requests are serialized to prevent duplication."""
        tasks = []

        # Launch 5 concurrent sells
        for _ in range(5):
            tasks.append(asyncio.create_task(
                self.cog._handle_sell("Player1", 1, 100, SERVER_CONF)
            ))

        await asyncio.gather(*tasks)

        # Check inserts
        insert_calls = 0
        for call in self.mock_db.execute.call_args_list:
            if "INSERT INTO market_listings" in call[0][0]:
                insert_calls += 1

        # With locking and state update, only 1 should succeed
        self.assertEqual(insert_calls, 1, "Race condition persisted! Duplicates created.")

if __name__ == '__main__':
    unittest.main()
