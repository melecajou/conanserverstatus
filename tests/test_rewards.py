import pytest
import aiosqlite
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

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
        self.mock_rcon_client = AsyncMock()
        self.mock_rcon_client.send_cmd = AsyncMock(return_value=("Success", None))

        self.db = await aiosqlite.connect(":memory:")
        await self.db.execute(
            """
            CREATE TABLE player_time (
                platform_id TEXT,
                server_name TEXT,
                online_minutes INTEGER DEFAULT 0,
                last_rewarded_hour INTEGER DEFAULT 0,
                discord_id TEXT,
                vip_level INTEGER DEFAULT 0,
                PRIMARY KEY (platform_id, server_name)
            )
        """
        )
        await self.db.executemany(
            "INSERT INTO player_time VALUES (?, ?, ?, ?, ?, ?)", PLAYER_DATA
        )
        await self.db.commit()

        self.rewards_cog = RewardsCog(self.mock_bot)
        self.rewards_cog.db_pools[SERVER_NAME] = self.db

    async def asyncTearDown(self):
        """Tear down the test environment after each test."""
        await self.db.close()

    async def test_regular_player_receives_reward(self):
        """
        Tests that a regular player who has met the playtime requirement receives a reward.
        """
        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        self.mock_rcon_client.send_cmd.assert_any_call("con 1 SpawnItem 12345 10")

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_rewarded_hour FROM player_time WHERE platform_id = 'steam_1'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 1)

    async def test_vip_player_receives_reward(self):
        """
        Tests that a VIP player who has met their accelerated playtime requirement receives a reward.
        """
        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        self.mock_rcon_client.send_cmd.assert_any_call("con 2 SpawnItem 12345 10")

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_rewarded_hour FROM player_time WHERE platform_id = 'steam_2'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 1)

    async def test_player_does_not_receive_reward(self):
        """
        Tests that a player who has not met the playtime requirement does not receive a reward.
        """
        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_rewarded_hour FROM player_time WHERE platform_id = 'steam_3'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 0)

    async def test_player_without_discord_id_is_skipped(self):
        """
        Tests that a player who has not linked their Discord account is skipped.
        """
        await self.rewards_cog._check_and_process_rewards(
            self.db,
            self.mock_rcon_client,
            SERVER_NAME,
            REWARD_CONFIG,
            ONLINE_PLAYERS,
        )

        async with self.db.cursor() as cur:
            await cur.execute(
                "SELECT last_rewarded_hour FROM player_time WHERE platform_id = 'steam_4'"
            )
            result = await cur.fetchone()
            self.assertEqual(result[0], 0)
