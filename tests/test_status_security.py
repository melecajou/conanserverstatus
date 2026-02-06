import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from cogs.status import StatusCog

class TestStatusSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.wait_until_ready = AsyncMock()

        with patch("discord.ext.tasks.Loop.start"):
             self.status_cog = StatusCog(self.mock_bot)

        self.mock_client = AsyncMock()
        self.mock_client.connect = AsyncMock()
        self.mock_client.close = AsyncMock()

        self.status_cog.rcon_clients["TestServer"] = self.mock_client
        self.status_cog.rcon_locks["TestServer"] = AsyncMock()
        self.status_cog.rcon_locks["TestServer"].__aenter__ = AsyncMock()
        self.status_cog.rcon_locks["TestServer"].__aexit__ = AsyncMock()

    async def test_execute_safe_command_injection_attempt(self):
        """Test that execute_safe_command raises ValueError if generated command contains banned characters."""

        # Return (response, request_id)
        # We simulate ListPlayers response first.
        # Note: calling get_player_list -> _execute_raw_rcon
        self.mock_client.send_cmd.side_effect = [
            ("0 | Victim | 1234567890 | | PlatformID", "1"),
            ("Success", "2")
        ]

        malicious_template = lambda idx: f"GiveItem {idx}; DROP TABLE users;"

        with self.assertRaises(ValueError) as cm:
            await self.status_cog.execute_safe_command(
                "TestServer",
                "Victim",
                malicious_template
            )

        self.assertIn("Security Alert: Banned characters detected", str(cm.exception))

    async def test_execute_safe_command_newline_injection(self):
        """Test injection with newline characters."""
        self.mock_client.send_cmd.side_effect = [
            ("0 | Victim | 1234567890 | | PlatformID", "1"),
            ("Success", "2")
        ]

        malicious_template = lambda idx: f"Say Hello\nAdminCommand"

        with self.assertRaises(ValueError) as cm:
            await self.status_cog.execute_safe_command(
                "TestServer",
                "Victim",
                malicious_template
            )

        self.assertIn("Security Alert: Banned characters detected", str(cm.exception))
