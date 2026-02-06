import pytest
import aiosqlite
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, ANY, patch

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
        # Mock batch data for Player One (steam_1)
        self.rewards_cog._fetch_batch_player_data = AsyncMock(return_value={
            "steam_1": {"online_minutes": 65, "last_reward_playtime": 0, "discord_id": "discord_1", "vip_level": 0}
        })

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
        # Mock batch data for VIP player (steam_2)
        self.rewards_cog._fetch_batch_player_data = AsyncMock(return_value={
            "steam_2": {"online_minutes": 35, "last_reward_playtime": 0, "discord_id": "discord_2", "vip_level": 1}
        })

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
        self.rewards_cog._fetch_batch_player_data = AsyncMock(return_value={
            "steam_3": {"online_minutes": 55, "last_reward_playtime": 0, "discord_id": "discord_3", "vip_level": 0}
        })

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
        # Mocking return dict where discord_id is None
        self.rewards_cog._fetch_batch_player_data = AsyncMock(return_value={
            "steam_4": {"online_minutes": 70, "last_reward_playtime": 0, "discord_id": None, "vip_level": 0}
        })

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

    async def test_fetch_batch_player_data_merges_correctly(self):
        """Test that local and global data are fetched and merged correctly."""
        # Mock global data return
        mock_global_data = {
            "steam_1": {"discord_id": "discord_1", "vip_level": 0, "vip_expiry": None},
            "steam_2": {"discord_id": "discord_2", "vip_level": 1, "vip_expiry": None},
        }

        # Add an extra local player not in global mock (should get defaults)
        await self.db.execute(
            "INSERT INTO player_time (platform_id, server_name, online_minutes, last_reward_playtime, discord_id, vip_level) VALUES (?, ?, ?, ?, ?, ?)",
            ("steam_only_local", SERVER_NAME, 10, 0, None, 0),
        )
        await self.db.commit()

        online_players_subset = [
            {"platform_id": "steam_1", "char_name": "P1", "idx": "1"},
            {"platform_id": "steam_2", "char_name": "P2", "idx": "2"},
            {"platform_id": "steam_only_local", "char_name": "P3", "idx": "3"},
            {"platform_id": "steam_missing_local", "char_name": "P4", "idx": "4"},
        ]

        # Patch utils.database.get_global_player_data
        with patch("utils.database.get_global_player_data", return_value=mock_global_data) as mock_get_global:
            # We call the REAL method here, not a mock of it
            # But we need to ensure we are calling the one bound to self.rewards_cog
            # Wait, the method is defined on the class, but we replaced it with AsyncMock in other tests?
            # NO, we replaced it on the INSTANCE `self.rewards_cog._fetch_batch_player_data = ...`
            # In THIS test, we haven't replaced it yet (assuming setUp creates a fresh instance or we didn't replace it in setUp).
            # setUp creates `self.rewards_cog = RewardsCog(self.mock_bot)`.
            # Other tests modify `self.rewards_cog`. Tests are isolated?
            # Yes, `IsolatedAsyncioTestCase` creates a new instance for each test method usually?
            # Actually `asyncSetUp` is called per test. So `self.rewards_cog` is fresh.

            batch_data = await self.rewards_cog._fetch_batch_player_data(
                self.db, SERVER_NAME, online_players_subset
            )

            # Assertions

            # steam_1: Merged correctly
            self.assertIn("steam_1", batch_data)
            self.assertEqual(batch_data["steam_1"]["online_minutes"], 65) # From setUp PLAYER_DATA
            self.assertEqual(batch_data["steam_1"]["discord_id"], "discord_1") # From mock_global

            # steam_2: Merged correctly
            self.assertIn("steam_2", batch_data)
            self.assertEqual(batch_data["steam_2"]["online_minutes"], 35) # From setUp PLAYER_DATA
            self.assertEqual(batch_data["steam_2"]["vip_level"], 1) # From mock_global

            # steam_only_local: Should exist with defaults for global
            self.assertIn("steam_only_local", batch_data)
            self.assertEqual(batch_data["steam_only_local"]["online_minutes"], 10)
            self.assertIsNone(batch_data["steam_only_local"]["discord_id"])
            self.assertEqual(batch_data["steam_only_local"]["vip_level"], 0)

            # steam_missing_local: Should NOT exist (filtered out because not in local DB)
            self.assertNotIn("steam_missing_local", batch_data)

            # Verify global fetch was called with correct IDs
            expected_ids = ["steam_1", "steam_2", "steam_only_local", "steam_missing_local"]
            mock_get_global.assert_called_once()
            call_args = mock_get_global.call_args[0][0]
            self.assertEqual(set(call_args), set(expected_ids))
