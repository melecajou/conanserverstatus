
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from discord.ext import commands
import sys

# Ensure cogs can be imported
import os
sys.path.append(os.getcwd())

class TestGuildSyncOptimization:

    @pytest.fixture
    def mock_bot(self):
        bot = MagicMock()
        bot._ = MagicMock()
        return bot

    @pytest.fixture
    def mock_guild(self):
        guild = MagicMock()
        guild.roles = []
        guild.fetch_members = AsyncMock()
        guild.get_member = MagicMock()
        guild.create_role = AsyncMock()
        return guild

    @pytest.mark.asyncio
    async def test_guild_sync_optimization(self, mock_bot, mock_guild):
        # Setup Data
        active_user_id = 123
        inactive_user_id = 456

        user_guild_map = {active_user_id: ["GuildA"]}

        # Mock Guild Roles
        role_a = MagicMock(spec=discord.Role)
        role_a.name = "🛡️ GuildA"
        role_a.members = []

        role_b = MagicMock(spec=discord.Role)
        role_b.name = "🛡️ GuildB"
        role_b.members = []

        mock_guild.roles = [role_a, role_b]

        # Mock Members
        # Active member: Has no roles, needs GuildA
        member_active = MagicMock(spec=discord.Member)
        member_active.id = active_user_id
        member_active.display_name = "ActiveUser"
        member_active.bot = False
        member_active.roles = []
        member_active.add_roles = AsyncMock()
        member_active.remove_roles = AsyncMock()

        # Inactive member: Has GuildB role, needs removal
        member_inactive = MagicMock(spec=discord.Member)
        member_inactive.id = inactive_user_id
        member_inactive.display_name = "InactiveUser"
        member_inactive.bot = False
        member_inactive.roles = [role_b]
        member_inactive.add_roles = AsyncMock()
        member_inactive.remove_roles = AsyncMock()

        # Setup role.members
        role_b.members = [member_inactive]

        # Setup get_member return
        def get_member_side_effect(uid):
            if uid == active_user_id:
                return member_active
            if uid == inactive_user_id:
                return member_inactive
            return None
        mock_guild.get_member.side_effect = get_member_side_effect

        mock_bot.get_guild.return_value = mock_guild

        # Patch config and get_all_guild_members
        with patch("config.GUILD_SYNC", {"ENABLED": True, "SERVER_ID": 1, "ROLE_PREFIX": "🛡️ "}, create=True), \
             patch("config.SERVERS", [{"DB_PATH": "dummy.db"}], create=True), \
             patch("cogs.guild_sync.get_all_guild_members", return_value=user_guild_map):

            from cogs.guild_sync import GuildSyncCog

            # Instantiate Cog
            cog = GuildSyncCog(mock_bot)

            # Run the task directly (await the coroutine logic)
            # Since sync_guilds_task is a loop, we access the coroutine and call it
            # But the loop decorator wraps it.
            # We can invoke the underlying function if available, or just call the method if we can stop the loop.
            # But wait, we didn't patch tasks.loop here.
            # If tasks.loop is active, creating Cog starts the loop!
            # We should patch tasks.loop to prevent auto-start or just cancel it.

            cog.sync_guilds_task.cancel() # Stop the background task

            # Now run the logic manually.
            # But sync_guilds_task is the loop object.
            # We need to call the callback.
            # In discord.py, loop.coro is the coroutine function.
            await cog.sync_guilds_task.coro(cog)

            # Assertions

            # 1. Verify fetch_members was NOT called (Optimization Check)
            mock_guild.fetch_members.assert_not_called()

            # 2. Verify get_member called for active user
            mock_guild.get_member.assert_any_call(active_user_id)

            # 3. Verify member_active got role added
            # We assume discord.utils.get finds role_a by name
            # Since mock_guild.roles has role_a with correct name

            assert member_active.add_roles.called
            args, _ = member_active.add_roles.call_args
            assert role_a in args

            # 4. Verify member_inactive got role removed
            assert member_inactive.remove_roles.called
            args, _ = member_inactive.remove_roles.call_args
            assert role_b in args
