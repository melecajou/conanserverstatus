import pytest
import sqlite3
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

from cogs.admin import AdminCog
import config

# Test data
SERVER_NAME = "Test Server"
PLAYER_DATA = [
    # A registered player
    ("steam_1", SERVER_NAME, 100, 1, "discord_123", 0),
]

class TestAdminCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Set up the test environment for each test."""
        self.mock_bot = MagicMock()
        # Correctly mock the translation function to return the key
        self.mock_bot._ = lambda s: s

        # The AdminCog uses synchronous sqlite3, so we'll use a file-based test database
        self.db_path = "test_admin.db"
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute(
                """
                CREATE TABLE player_time (
                    platform_id TEXT,
                    server_name TEXT,
                    online_minutes INTEGER DEFAULT 0,
                    last_rewarded_hour INTEGER DEFAULT 0,
                    discord_id TEXT,
                    vip_level INTEGER DEFAULT 0,
                    vip_expiry_date TEXT,
                    PRIMARY KEY (platform_id, server_name)
                )
            """
            )
            cur.executemany(
                "INSERT INTO player_time (platform_id, server_name, online_minutes, last_rewarded_hour, discord_id, vip_level) VALUES (?, ?, ?, ?, ?, ?)",
                PLAYER_DATA,
            )
            con.commit()

        self.admin_cog = AdminCog(self.mock_bot)

        # We need to patch the config to use our test database
        config.SERVERS = [{"NAME": SERVER_NAME, "PLAYER_DB_PATH": self.db_path}]

        # Mock the interaction object
        self.mock_interaction = AsyncMock()
        self.mock_interaction.response = AsyncMock()
        self.mock_interaction.guild.name = SERVER_NAME

    async def asyncTearDown(self):
        """Tear down the test environment after each test."""
        import os
        os.remove(self.db_path)

    async def test_set_vip_for_registered_player(self):
        """
        Tests that a VIP level can be successfully set for a registered player.
        """
        mock_member = MagicMock()
        mock_member.id = "discord_123"
        mock_member.display_name = "Test User"

        await self.admin_cog.set_vip_command.callback(self.admin_cog, self.mock_interaction, mock_member, 1)

        self.mock_interaction.followup.send.assert_called_with(
            "VIP level for '{member}' updated to {level}.".format(member="Test User", level=1),
            ephemeral=True
        )

        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT vip_level, vip_expiry_date FROM player_time WHERE discord_id = 'discord_123'")
            result = cur.fetchone()
            self.assertEqual(result[0], 1)
            self.assertIsNotNone(result[1])

    async def test_set_vip_for_unregistered_player(self):
        """
        Tests the command's behavior when used on a Discord user who is not yet registered.
        """
        mock_member = MagicMock()
        mock_member.id = "discord_456"
        mock_member.display_name = "Unregistered User"

        await self.admin_cog.set_vip_command.callback(self.admin_cog, self.mock_interaction, mock_member, 1)

        self.mock_interaction.followup.send.assert_called_with(
            "No linked game account was found for the member '{member}'. The user must first use the /register command.".format(member="Unregistered User"),
            ephemeral=True,
        )

    async def test_set_negative_vip_level(self):
        """
        Tests that a negative VIP level is handled correctly.
        """
        mock_member = MagicMock()
        mock_member.id = "discord_123"
        mock_member.display_name = "Test User"

        await self.admin_cog.set_vip_command.callback(self.admin_cog, self.mock_interaction, mock_member, -1)

        self.mock_interaction.followup.send.assert_called_with(
            "The VIP level cannot be negative.", ephemeral=True
        )
