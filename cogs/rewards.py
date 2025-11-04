import asyncio
import logging
from typing import List, Dict, Any

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
        """Parses raw player lines into a list of player dictionaries."""
        online_players = []
        for line in player_lines:
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) > 4:
                online_players.append({
                    "idx": parts[0].strip(),
                    "char_name": parts[1].strip(),
                    "platform_id": parts[4].strip()
                })
        return online_players

    async def _update_playtime(self, db: aiosqlite.Connection, server_name: str, online_players: List[Dict[str, str]]):
        """Updates the playtime for all online players."""
        async with db.cursor() as cur:
            for player in online_players:
                platform_id = player["platform_id"]
                await cur.execute("INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)",
                                  (platform_id, server_name))
                await cur.execute(
                    "UPDATE player_time SET online_minutes = online_minutes + 1 WHERE platform_id = ? AND server_name = ?",
                    (platform_id, server_name))
        await db.commit()

    async def _issue_reward(self, rcon_client: Any, server_name: str, player: Dict[str, Any],
                            reward_config: Dict[str, Any]):
        """Issues a reward to a single player and updates the database."""
        item_id = reward_config["REWARD_ITEM_ID"]
        quantity = reward_config["REWARD_QUANTITY"]
        command = f"con {player['idx']} SpawnItem {item_id} {quantity}"

        for attempt in range(3):
            try:
                response, _ = await rcon_client.send_cmd(command)
                logging.info(
                    self._(
                        f"Reward command '{command}' for player {player['char_name']} on server '{server_name}' executed. Response: {response.strip()}"))
                return True
            except Exception as e:
                logging.warning(
                    self._(f"Attempt {attempt + 1}/3 to send reward for player {player['char_name']} failed: {e}"))
                await asyncio.sleep(2)  # Wait before retrying

        logging.error(
            self._(
                f"Failed to send reward RCON command for player {player['char_name']} on server '{server_name}' after 3 attempts."))
        return False

    async def _check_and_process_rewards(self, db: aiosqlite.Connection, rcon_client: Any, server_name: str,
                                         reward_config: Dict[str, Any], online_players: List[Dict[str, str]]):
        """Checks for and processes rewards for all online players."""
        reward_intervals = reward_config.get('INTERVALS_MINUTES', {0: 120})

        async with db.cursor() as cur:
            for player in online_players:
                platform_id = player["platform_id"]
                await cur.execute(
                    "SELECT online_minutes, last_rewarded_hour, discord_id, vip_level FROM player_time WHERE platform_id = ? AND server_name = ?",
                    (platform_id, server_name))
                result = await cur.fetchone()

                if not result or result[2] is None or result[2] == '':
                    continue

                online_minutes, last_rewarded_hour, _, vip_level = result
                reward_interval = reward_intervals.get(vip_level, reward_intervals.get(0, 120))
                current_hour_milestone = online_minutes // reward_interval

                if current_hour_milestone > last_rewarded_hour:
                    total_hours_played = current_hour_milestone * (reward_interval / 60.0)
                    logging.info(self._(
                        f"Player {player['char_name']} on server '{server_name}' reached a new reward milestone at {total_hours_played:.1f} hours. Issuing reward."))

                    if await self._issue_reward(rcon_client, server_name, player, reward_config):
                        await cur.execute(
                            "UPDATE player_time SET last_rewarded_hour = ? WHERE platform_id = ? AND server_name = ?",
                            (current_hour_milestone, platform_id, server_name))
                        await db.commit()
                        logging.info(self._(
                            f"Player {player['char_name']} on server '{server_name}' has been rewarded."
                        ))

    @commands.Cog.listener()
    async def on_conan_players_updated(self, server_conf: dict, player_lines: List[str], rcon_client):
        """This event is dispatched by the StatusCog and triggers the reward logic."""
        reward_config = server_conf.get('REWARD_CONFIG', {})
        if not reward_config.get('ENABLED', False):
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
            await self._check_and_process_rewards(db, rcon_client, server_name, reward_config, online_players)
        except Exception as e:
            logging.error(f"An error occurred in track_and_reward_players for server '{server_name}': {e}")


async def setup(bot):
    cog = RewardsCog(bot)
    await cog.async_init()
    await bot.add_cog(cog)
