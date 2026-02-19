import asyncio
import logging
from typing import List, Dict, Any, Optional

import aiosqlite
import config
from discord.ext import commands

from utils.database import DEFAULT_PLAYER_TRACKER_DB


class RewardsCog(commands.Cog, name="Rewards"):
    """Handles player rewards and playtime tracking."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.db_pools: Dict[str, aiosqlite.Connection] = {}

    async def async_init(self):
        """Asynchronous initialization for the cog."""
        for server_config in config.SERVERS:
            db_path = server_config.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
            self.db_pools[server_config["NAME"]] = await aiosqlite.connect(db_path)

    def _parse_player_lines(self, player_lines: List[str]) -> List[Dict[str, str]]:
        """
        Parses raw player lines from the RCON `playerlist` command into a list of player dictionaries.

        Args:
            player_lines: A list of strings, where each string represents a line of player data.

        Returns:
            A list of dictionaries, where each dictionary represents an online player.
        """
        online_players = []
        for line in player_lines:
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) > 4:
                online_players.append(
                    {
                        "idx": parts[0].strip(),
                        "char_name": parts[1].strip(),
                        "platform_id": parts[4].strip(),
                    }
                )
        return online_players

    async def _update_playtime(
        self,
        db: aiosqlite.Connection,
        server_name: str,
        online_players: List[Dict[str, str]],
    ):
        """
        Updates the playtime for all online players in the database.

        Args:
            db: The database connection.
            server_name: The name of the server.
            online_players: A list of dictionaries representing the online players.
        """
        data = [(p["platform_id"], server_name, 1) for p in online_players]
        if not data:
            return

        async with db.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO player_time (platform_id, server_name, online_minutes)
                VALUES (?, ?, ?)
                ON CONFLICT(platform_id, server_name)
                DO UPDATE SET online_minutes = online_minutes + 1
                """,
                data,
            )
        await db.commit()

    async def _issue_reward(
        self,
        rcon_client: Any,
        server_name: str,
        player: Dict[str, Any],
        reward_config: Dict[str, Any],
    ) -> bool:
        """
        Issues a reward to a single player and updates the database.
        """
        item_id = reward_config["REWARD_ITEM_ID"]
        quantity = reward_config["REWARD_QUANTITY"]

        status_cog = self.bot.get_cog("Status")
        if not status_cog:
            logging.error("StatusCog not found for reward execution.")
            return False

        try:
            # Use execute_safe_command to handle race conditions and retries
            await status_cog.execute_safe_command(
                server_name,
                player["char_name"],
                lambda idx: f"con {idx} SpawnItem {item_id} {quantity}",
            )

            logging.info(
                self._("Reward issued to player %s on server '%s' (Item: %s, Qty: %s)")
                % (player["char_name"], server_name, item_id, quantity)
            )
            return True
        except Exception as e:
            logging.error(
                self._("Failed to issue reward for player %s on server '%s': %s")
                % (player["char_name"], server_name, e)
            )
            return False

    async def _fetch_batch_player_data(
        self,
        db: aiosqlite.Connection,
        server_name: str,
        online_players: List[Dict[str, str]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetches local and global data for all online players in batch.

        Returns:
             A dictionary mapping platform_id to a dict containing:
             - online_minutes (int)
             - last_reward_playtime (int)
             - discord_id (int or None)
             - vip_level (int)
             - vip_expiry (str or None)
        """
        platform_ids = [p["platform_id"] for p in online_players]
        if not platform_ids:
            return {}

        # 1. Fetch Local Data (Async)
        local_data = {}
        try:
            async with db.cursor() as cur:
                placeholders = ", ".join("?" * len(platform_ids))
                query = f"SELECT platform_id, online_minutes, last_reward_playtime FROM player_time WHERE platform_id IN ({placeholders}) AND server_name = ?"
                await cur.execute(query, platform_ids + [server_name])
                rows = await cur.fetchall()
                for pid, mins, last_rew in rows:
                    local_data[pid] = {
                        "online_minutes": mins,
                        "last_reward_playtime": last_rew,
                    }
        except Exception as e:
            logging.error(f"Error batch fetching local player data: {e}")
            return {}

        # 2. Fetch Global Data (Sync in Thread)
        from utils.database import get_global_player_data

        try:
            global_data = await asyncio.to_thread(get_global_player_data, platform_ids)
        except Exception as e:
            logging.error(f"Error batch fetching global player data: {e}")
            global_data = {}

        # 3. Merge Data
        merged_data = {}
        for pid in platform_ids:
            if pid not in local_data:
                continue

            l_data = local_data[pid]
            g_data = global_data.get(
                pid, {"discord_id": None, "vip_level": 0, "vip_expiry": None}
            )

            merged_data[pid] = {**l_data, **g_data}

        return merged_data

    async def _check_and_process_rewards(
        self,
        db: aiosqlite.Connection,
        rcon_client: Any,
        server_name: str,
        reward_config: Dict[str, Any],
        online_players: List[Dict[str, str]],
    ):
        """
        Checks for and processes rewards for all online players.

        Args:
            db: The database connection.
            rcon_client: The RCON client for the server.
            server_name: The name of the server.
            reward_config: The reward configuration for the server.
            online_players: A list of dictionaries representing the online players.
        """
        from datetime import datetime

        if "INTERVALS_MINUTES" in reward_config:
            reward_intervals = reward_config["INTERVALS_MINUTES"]
        else:
            default_interval = reward_config.get("REWARD_INTERVAL_MINUTES", 120)
            reward_intervals = {0: default_interval}

        # Fetch all data in batch
        batch_data = await self._fetch_batch_player_data(
            db, server_name, online_players
        )

        for player in online_players:
            platform_id = player["platform_id"]
            if platform_id not in batch_data:
                continue

            data = batch_data[platform_id]
            discord_id = data.get("discord_id")

            # Must have a linked Discord ID to receive rewards
            if not discord_id:
                continue

            online_minutes = data["online_minutes"]
            last_reward_playtime = data["last_reward_playtime"]
            vip_level = data.get("vip_level", 0)
            vip_expiry = data.get("vip_expiry")

            # Check for expiration
            if vip_level > 0 and vip_expiry:
                try:
                    expiry_dt = datetime.fromisoformat(vip_expiry)
                    if datetime.now() > expiry_dt:
                        logging.debug(
                            f"VIP Rewards expired for player {platform_id} (Discord: {discord_id}). Treating as Level 0 for rewards."
                        )
                        vip_level = 0
                except (ValueError, TypeError):
                    logging.warning(
                        f"Invalid expiry date format for Discord ID {discord_id}: {vip_expiry}"
                    )

            reward_interval = reward_intervals.get(
                vip_level, reward_intervals.get(0, 120)
            )

            # Check if enough time has passed since the last reward
            if (online_minutes - last_reward_playtime) >= reward_interval:
                total_hours_played = online_minutes / 60.0
                logging.info(
                    self._(
                        "Player %s on server '%s' reached a new reward milestone at %.1f hours. Issuing reward."
                    )
                    % (player["char_name"], server_name, total_hours_played)
                )

                if await self._issue_reward(
                    rcon_client, server_name, player, reward_config
                ):
                    async with db.cursor() as cur:
                        await cur.execute(
                            "UPDATE player_time SET last_reward_playtime = ? WHERE platform_id = ? AND server_name = ?",
                            (online_minutes, platform_id, server_name),
                        )
                    await db.commit()
                    logging.info(
                        self._("Player %s on server '%s' has been rewarded.")
                        % (player["char_name"], server_name)
                    )

    @commands.Cog.listener()
    async def on_conan_players_updated(
        self, server_conf: dict, player_lines: List[str], rcon_client
    ):
        """
        This event is dispatched by the StatusCog and triggers the reward logic.

        Args:
            server_conf: The configuration for the server.
            player_lines: A list of strings, where each string represents a line of player data.
            rcon_client: The RCON client for the server.
        """
        reward_config = server_conf.get("REWARD_CONFIG", {})
        if not reward_config.get("ENABLED", False):
            return

        server_name = server_conf["NAME"]
        online_players = self._parse_player_lines(player_lines)

        if not online_players:
            return

        db = self.db_pools.get(server_name)
        if not db:
            logging.error(f"Database pool not found for server: {server_name}")
            return

        try:
            await self._update_playtime(db, server_name, online_players)
            await self._check_and_process_rewards(
                db, rcon_client, server_name, reward_config, online_players
            )
        except Exception as e:
            logging.error(
                f"An error occurred in track_and_reward_players for server '{server_name}': {e}"
            )


async def setup(bot):
    cog = RewardsCog(bot)
    await cog.async_init()
    await bot.add_cog(cog)
