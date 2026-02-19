import pytest
import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from aiomcrcon import RCONConnectionError, IncorrectPasswordError

from cogs.status import StatusCog
import config

SERVER_NAME = "Test Server"
SERVER_CONF = {
    "NAME": SERVER_NAME,
    "ENABLED": True,
    "SERVER_IP": "127.0.0.1",
    "RCON_PORT": 25575,
    "RCON_PASS": "password",
    "STATUS_CHANNEL_ID": 123456789,
    "LOG_PATH": None,
    "DB_PATH": ":memory:",
}


class TestStatusCog(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot._ = lambda s: s
        self.mock_bot.get_channel = MagicMock()
        self.mock_bot.wait_until_ready = AsyncMock()
        self.mock_bot.change_presence = AsyncMock()

        # Patch config.SERVERS
        self.config_patcher = patch("config.SERVERS", [SERVER_CONF])
        self.config_patcher.start()

        # Patch the task start to prevent it from running automatically
        with patch("discord.ext.tasks.Loop.start"):
            self.status_cog = StatusCog(self.mock_bot)

        # Manually init to setup locks, but ensure we control the client creation
        # We can just manually set them up instead of calling async_init
        # self.status_cog.async_init() creates clients.

        # Mock the RCON client for the server
        self.mock_client = AsyncMock()
        self.status_cog.rcon_clients[SERVER_NAME] = self.mock_client
        self.status_cog.rcon_locks[SERVER_NAME] = asyncio.Lock()

    async def asyncTearDown(self):
        # Stop the task if it was started
        self.status_cog.update_all_statuses_task.cancel()
        self.config_patcher.stop()

    async def test_execute_raw_rcon_success(self):
        """Test successful RCON execution."""
        self.mock_client.connect.return_value = None
        self.mock_client.send_cmd.return_value = ("Success", 1)

        response, _ = await self.status_cog._execute_raw_rcon(SERVER_NAME, "status")

        self.assertEqual(response, "Success")
        self.mock_client.connect.assert_called()
        self.mock_client.send_cmd.assert_called_with("status")

    async def test_execute_raw_rcon_retry_success(self):
        """Test RCON retry logic (fail once, then succeed)."""
        # First attempt fails, second succeeds
        self.mock_client.connect.side_effect = [RCONConnectionError("Fail"), None]
        self.mock_client.send_cmd.return_value = ("Success", 1)

        response, _ = await self.status_cog._execute_raw_rcon(SERVER_NAME, "status")

        self.assertEqual(response, "Success")
        self.assertEqual(self.mock_client.connect.call_count, 2)

    async def test_execute_raw_rcon_fail_max_retries(self):
        """Test RCON failure after max retries."""
        self.mock_client.connect.side_effect = RCONConnectionError("Fail")

        with self.assertRaises(RCONConnectionError):
            await self.status_cog._execute_raw_rcon(
                SERVER_NAME, "status", max_retries=2
            )

        self.assertEqual(self.mock_client.connect.call_count, 3)  # Initial + 2 retries

    async def test_execute_safe_command_success(self):
        """Test successful safe command execution."""
        # 1. _execute_raw_rcon for ListPlayers
        # 2. _execute_raw_rcon for Command

        # Mock _execute_raw_rcon on the instance
        self.status_cog._execute_raw_rcon = AsyncMock()
        # Ensure data has enough parts (>4)
        self.status_cog._execute_raw_rcon.side_effect = [
            ("5 | TestPlayer | A | B | steam_id", None),  # ListPlayers response
            ("Command Executed", None),  # Command response
        ]

        await self.status_cog.execute_safe_command(
            SERVER_NAME, "TestPlayer", lambda idx: f"kick {idx}"
        )

        self.assertEqual(self.status_cog._execute_raw_rcon.call_count, 2)
        self.status_cog._execute_raw_rcon.assert_any_call(SERVER_NAME, "ListPlayers")
        # Ensure correct index was used
        self.status_cog._execute_raw_rcon.assert_any_call(
            SERVER_NAME, "kick 5", max_retries=0
        )

    async def test_execute_safe_command_retry_loop(self):
        """Test safe command execution retrying the whole loop when command fails."""
        # Loop 1:
        #   ListPlayers -> OK (returns idx 5)
        #   Command (kick 5) -> Fails (Simulating stale index)
        # Loop 2:
        #   ListPlayers -> OK (returns idx 6 - player relogged)
        #   Command (kick 6) -> Success

        self.status_cog._execute_raw_rcon = AsyncMock()
        self.status_cog._execute_raw_rcon.side_effect = [
            ("5 | TestPlayer | A | B | steam_id", None),  # Loop 1: ListPlayers
            RCONConnectionError("Failed"),  # Loop 1: Command fails
            ("6 | TestPlayer | A | B | steam_id", None),  # Loop 2: ListPlayers
            ("Command Executed", None),  # Loop 2: Command succeeds
        ]

        await self.status_cog.execute_safe_command(
            SERVER_NAME, "TestPlayer", lambda idx: f"kick {idx}"
        )

        self.assertEqual(self.status_cog._execute_raw_rcon.call_count, 4)
        # Check calls
        calls = self.status_cog._execute_raw_rcon.call_args_list
        self.assertEqual(calls[0][0], (SERVER_NAME, "ListPlayers"))
        self.assertEqual(calls[1][0], (SERVER_NAME, "kick 5"))
        self.assertEqual(calls[2][0], (SERVER_NAME, "ListPlayers"))
        self.assertEqual(calls[3][0], (SERVER_NAME, "kick 6"))

    async def test_execute_safe_command_player_not_found(self):
        """Test safe command failing when player is not found."""
        self.status_cog._execute_raw_rcon = AsyncMock(
            return_value=("99 | OtherGuy | A | B | id", None)
        )

        with self.assertRaises(ValueError):
            await self.status_cog.execute_safe_command(
                SERVER_NAME, "TestPlayer", lambda idx: f"kick {idx}"
            )

    async def test_export_status_json(self):
        """Test the _export_status_json method logic."""
        cluster_data = [
            {
                "name": "Test Server",
                "alias": "Test",
                "online_players": [{"char_name": "Player1", "platform_id": "Pid1"}],
                "levels_map": {"Player1": 60},
                "player_data_map": {"Pid1": {"online_minutes": 100}},
                "system_stats": {},
            }
        ]
        server_statuses = [{"alias": "Test", "online": True, "fps": "60"}]

        # Mock _write_json_file on the instance to verify it's called
        self.status_cog._write_json_file = MagicMock()

        await self.status_cog._export_status_json(cluster_data, server_statuses)

        self.status_cog._write_json_file.assert_called_once()
        args, _ = self.status_cog._write_json_file.call_args
        # Normalize path separators for cross-platform compatibility
        self.assertIn("output/status.json", args[0].replace("\\", "/"))
        self.assertEqual(args[1]["servers"][0]["name"], "Test Server")

    def test_write_json_file(self):
        """Test the static _write_json_file method."""
        import json
        import os
        import tempfile

        test_data = {"test": "data", "nested": [1, 2, 3]}

        with tempfile.TemporaryDirectory() as tmpdirname:
            test_path = os.path.join(tmpdirname, "test_output.json")

            StatusCog._write_json_file(test_path, test_data)

            self.assertTrue(os.path.exists(test_path))
            with open(test_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            self.assertEqual(content, test_data)

    async def test_get_player_list_caching(self):
        """Test that get_player_list caches the response."""
        # Setup mock for _execute_raw_rcon
        self.status_cog._execute_raw_rcon = AsyncMock(return_value=("List1", None))

        # 1. First call: Cache miss
        with patch("time.time", return_value=1000):
            resp1, _ = await self.status_cog.get_player_list(SERVER_NAME, use_cache=True)
            self.assertEqual(resp1, "List1")
            self.status_cog._execute_raw_rcon.assert_called_once()

            # 2. Second call: Cache hit (within TTL)
            # Reset mock to verify it's NOT called
            self.status_cog._execute_raw_rcon.reset_mock()
            resp2, _ = await self.status_cog.get_player_list(SERVER_NAME, use_cache=True)
            self.assertEqual(resp2, "List1")
            self.status_cog._execute_raw_rcon.assert_not_called()

        # 3. Third call: Cache expired (TTL is 0.5s)
        with patch("time.time", return_value=1000.6):
            self.status_cog._execute_raw_rcon.reset_mock()
            self.status_cog._execute_raw_rcon.return_value = ("List2", None)

            resp3, _ = await self.status_cog.get_player_list(SERVER_NAME, use_cache=True)
            self.assertEqual(resp3, "List2")
            self.status_cog._execute_raw_rcon.assert_called_once()

        # 4. Fourth call: Force refresh (use_cache=False)
        with patch("time.time", return_value=1004):
            self.status_cog._execute_raw_rcon.reset_mock()
            self.status_cog._execute_raw_rcon.return_value = ("List3", None)

            resp4, _ = await self.status_cog.get_player_list(SERVER_NAME, use_cache=False)
            self.assertEqual(resp4, "List3")
            self.status_cog._execute_raw_rcon.assert_called_once()
