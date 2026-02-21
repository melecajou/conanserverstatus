import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import os
import sys

# Ensure config passes validation (as bot import runs validation)
# We assume config.py exists because we created it in previous step.
# If not, we might need to rely on conftest or patch before import.
# But since verification script passed, config.py is there.

from cogs.registration import RegistrationCog
import config

class TestRegistrationSync(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_linked_discord_ids(self):
        # Mock sqlite3
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor

            # Setup mock data
            # Query: SELECT DISTINCT discord_id FROM player_time WHERE discord_id IS NOT NULL
            mock_cursor.fetchall.return_value = [("12345",), ("67890",), (None,)]

            # Mock os.path.exists to return True
            with patch("os.path.exists", return_value=True):
                servers = [{"PLAYER_DB_PATH": "test.db"}]

                # Call the static method directly
                ids = await asyncio.to_thread(RegistrationCog._fetch_all_linked_discord_ids, servers)

                self.assertEqual(ids, {12345, 67890})
                mock_connect.assert_called_with("test.db")

    async def test_sync_roles_command(self):
        bot = MagicMock()
        # Mock task in __init__
        with patch("discord.ext.tasks.Loop.start"):
            cog = RegistrationCog(bot)

        # Mock interaction
        interaction = AsyncMock()
        interaction.guild = MagicMock()
        role = MagicMock()
        interaction.guild.get_role.return_value = role
        interaction.guild.fetch_member = AsyncMock()

        # Mock fetch_member to return a valid member
        member = MagicMock()
        member.roles = []
        member.add_roles = AsyncMock()
        interaction.guild.fetch_member.return_value = member

        # Mock config
        with patch("config.REGISTERED_ROLE_ID", 999, create=True):
             # Mock fetch_all_linked_discord_ids to return a set of IDs
            with patch.object(RegistrationCog, "_fetch_all_linked_discord_ids", return_value={12345}) as mock_fetch:

                # Execute command
                await cog.sync_roles_command.callback(cog, interaction)

                # Verify fetch called
                mock_fetch.assert_called_once()

                # Verify interaction deferred
                interaction.response.defer.assert_called_once_with(ephemeral=True)

                # Verify fetch_member called
                interaction.guild.fetch_member.assert_called_with(12345)

                # Verify roles added
                member.add_roles.assert_called_with(role)

                # Verify confirmation sent
                interaction.followup.send.assert_called()
