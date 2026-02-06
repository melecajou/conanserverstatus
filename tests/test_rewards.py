import pytest
import aiosqlite
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, ANY

from cogs.rewards import RewardsCog

# Basic configuration for the tests
SERVER_NAME = "Test Server"
REWARD_CONFIG = {
    "ENABLED": True,
    "REWARD_ITEM_ID": 12345,
    "REWARD_QUANTITY": 10,
    "INTERVALS_MINUTES": {
        0: 60,  # 60 minutes for regular players
        1: 30,  # 30 minutes for VIP level 1
    },
}

# Player data for our tests
PLAYER_DATA = [
    # Player 1: Regular player, eligible for a reward
    ("steam_1", SERVER_NAME, 65, 0, "discord_1", 0),
    # Player 2: VIP player, eligible for a reward
    ("steam_2", SERVER_NAME, 35, 0, "discord_2", 1),
    # Player 3: Regular player, not yet eligible for a reward
    ("steam_3", SERVER_NAME, 55, 0, "discord_3", 0),
    # Player 4: Player who has not linked their Discord account
    ("steam_4", SERVER_NAME, 70, 0, None, 0),
]

# Online players for our tests
ONLINE_PLAYERS = [
    {"idx": "1", "char_name": "Player One", "platform_id": "steam_1"},
    {"idx": "2", "char_name": "Player Two", "platform_id": "steam_2"},
    {"idx": "3", "char_name": "Player Three", "platform_id": "steam_3"},
    {"idx": "4", "char_name": "Player Four", "platform_id": "steam_4"},
]


class TestRewardsCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Set up the test environment for each test."""
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s

        # Setup Mock StatusCog for RCON execution
        self.mock_status_cog = MagicMock()
        self.mock_status_cog.execute_rcon = AsyncMock(return_value=("Success", None))
        self.mock_status_cog.execute_safe_command = AsyncMock(
            return_value=("Success", None)
        )

        # Configure bot.get_cog to return our mock
        self.mock_bot.get_cog = MagicMock(return_value=self.mock_status_cog)

        self.mock_rcon_client = AsyncMock()  # This is passed but unused by code

        self.db = await aiosqlite.connect(":memory:")
        # Updated schema to match utils/database.py initialization
        await self.db.execute("""
            CREATE TABLE player_time (
                platform_id TEXT,
                server_name TEXT,
                online_minutes INTEGER DEFAULT 0,
                last_rewarded_hour INTEGER DEFAULT 0,
                last_reward_playtime INTEGER DEFAULT 0,
                discord_id TEXT,
                vip_level INTEGER DEFAULT 0,
                PRIMARY KEY (platform_id, server_name)
            )
        """)
        await self.db.executemany(
            "INSERT INTO player_time (platform_id, server_name, online_minutes, last_reward_playtime, discord_id, vip_level) VALUES (?, ?, ?, ?, ?, ?)",
            PLAYER_DATA,
        )
        await self.db.commit()

        self.rewards_cog = RewardsCog(self.mock_bot)
        self.rewards_cog.db_pools[SERVER_NAME] = self.db

    async def asyncTearDown(self):
        """Tear down the test environment after each test."""
        await self.db.close()

    async def test_regular_player_receives_reward(self):
        # We need to mock _get_player_reward_status because it tries to read global DB
        self.rewards_cog._get_player_reward_status = AsyncMock(return_value=(65, 0, 60))

        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        # Check that StatusCog.execute_safe_command was called for Player One
        self.mock_status_cog.execute_safe_command.assert_any_call(
            SERVER_NAME, "Player One", ANY
        )

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_reward_playtime FROM player_time WHERE platform_id = 'steam_1'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 65)

    async def test_vip_player_receives_reward(self):
        # Mocking VIP player status (35 minutes played, interval 30)
        self.rewards_cog._get_player_reward_status = AsyncMock(return_value=(35, 0, 30))

        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        self.mock_status_cog.execute_safe_command.assert_any_call(
            SERVER_NAME, "Player Two", ANY
        )

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_reward_playtime FROM player_time WHERE platform_id = 'steam_2'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 35)

    async def test_player_does_not_receive_reward(self):
        # Mocking player not yet eligible (55 mins played, interval 60)
        self.rewards_cog._get_player_reward_status = AsyncMock(return_value=(55, 0, 60))

        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_reward_playtime FROM player_time WHERE platform_id = 'steam_3'"
            )
            result = await cur.fetchone()
            # Should remain 0
            self.assertEqual(result[0], 0)

    async def test_player_without_discord_id_is_skipped(self):
        # Mocking return None (not registered)
        self.rewards_cog._get_player_reward_status = AsyncMock(return_value=None)

        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_reward_playtime FROM player_time WHERE platform_id = 'steam_4'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 0)
