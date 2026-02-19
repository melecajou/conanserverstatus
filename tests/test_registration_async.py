import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from cogs.registration import RegistrationCog
from utils.database import link_discord_to_character, link_discord_to_platform

class TestRegistrationAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot._ = lambda s: s # Mock translation

        # Patch the task loop start to prevent it from running
        # We need to patch before creating the Cog because __init__ calls start()
        with patch('discord.ext.tasks.Loop.start'):
            self.cog = RegistrationCog(self.bot)

        # Ensure the loop task is cancelled if it started (just in case)
        if hasattr(self.cog, 'process_registration_log_task'):
             self.cog.process_registration_log_task.cancel()

    async def test_link_account_async_calls(self):
        """Verify _link_account_and_notify uses asyncio.to_thread for blocking calls."""

        # Patch asyncio.to_thread where it is used in cogs.registration
        with patch('cogs.registration.asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
            # Setup return values for the sequence of calls
            # 1. link_discord_to_character -> True
            # 2. _get_platform_id_sync -> "Steam_123"
            # 3. link_discord_to_platform -> True
            # Note: side_effect can be an iterable of return values
            mock_to_thread.side_effect = [True, "Steam_123", True]

            # Mock fetch_user so it doesn't fail
            mock_user = MagicMock()
            mock_user.send = AsyncMock()
            self.bot.fetch_user = AsyncMock(return_value=mock_user)
            self.bot._ = lambda s: s # Mock translation

            # Call the method
            await self.cog._link_account_and_notify(
                code="CODE123",
                discord_id=12345,
                char_name="TestChar",
                player_db_path="player.db",
                game_db_path="game.db",
                server_name="TestServer"
            )

            # Verify calls
            self.assertEqual(mock_to_thread.call_count, 3, "Expected 3 asyncio.to_thread calls")

            # Check arguments for first call (link_discord_to_character)
            args, _ = mock_to_thread.call_args_list[0]
            # Since link_discord_to_character is imported in cogs.registration, we check against that reference
            # However, imports are objects, so identity check is fine if it's the same function
            self.assertEqual(args[0], link_discord_to_character)

            # Check arguments for second call (_get_platform_id_sync)
            args, _ = mock_to_thread.call_args_list[1]
            # Verify it's the static method
            self.assertEqual(args[0], self.cog._get_platform_id_sync)

            # Check arguments for third call (link_discord_to_platform)
            args, _ = mock_to_thread.call_args_list[2]
            self.assertEqual(args[0], link_discord_to_platform)
