import pytest
import sqlite3
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.admin import AdminCog
import config

# Test data
SERVER_NAME = "Test Server"


class TestAdminCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Set up the test environment for each test."""
        self.mock_bot = MagicMock()
        # Correctly mock the translation function to return the key
        self.mock_bot._ = lambda s: s

        self.admin_cog = AdminCog(self.mock_bot)

        # Mock the interaction object
        self.mock_interaction = AsyncMock()
        self.mock_interaction.response = AsyncMock()
        self.mock_interaction.guild.name = SERVER_NAME
        self.mock_interaction.user.id = 12345

    async def asyncTearDown(self):
        """Tear down the test environment after each test."""
        pass

    async def test_set_vip_success(self):
        """
        Tests that a VIP level can be successfully set using the global DB function.
        """
        mock_member = MagicMock()
        mock_member.id = 123
        mock_member.display_name = "Test User"

        # Mock utils.database.set_global_vip to avoid real DB writes
        with patch("utils.database.set_global_vip", return_value=True) as mock_set_vip:
            await self.admin_cog.setvip.callback(
                self.admin_cog, self.mock_interaction, mock_member, 1
            )

            # Check if it was called with correct ID and Level
            mock_set_vip.assert_called_once()
            args = mock_set_vip.call_args[0]
            self.assertEqual(args[0], 123)
            self.assertEqual(args[1], 1)

        self.mock_interaction.response.send_message.assert_called()
        msg = self.mock_interaction.response.send_message.call_args[0][0]
        self.assertIn("updated to 1", msg)

    async def test_set_vip_failure(self):
        """
        Tests behavior when DB update fails.
        """
        mock_member = MagicMock()
        mock_member.id = 456
        mock_member.display_name = "Fail User"

        with patch("utils.database.set_global_vip", return_value=False):
            await self.admin_cog.setvip.callback(
                self.admin_cog, self.mock_interaction, mock_member, 1
            )

        self.mock_interaction.response.send_message.assert_called()
        args, kwargs = self.mock_interaction.response.send_message.call_args
        self.assertIn("An error occurred", args[0])
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_set_negative_vip_level(self):
        """
        Tests that a negative VIP level is handled correctly.
        """
        mock_member = MagicMock()
        mock_member.id = 123

        await self.admin_cog.setvip.callback(
            self.admin_cog, self.mock_interaction, mock_member, -1
        )

        self.mock_interaction.response.send_message.assert_called_with(
            "The VIP level cannot be negative.", ephemeral=True
        )
