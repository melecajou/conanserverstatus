import config
from database import DEFAULT_PLAYER_TRACKER_DB
from discord.ext import commands
import logging
import sqlite3
from typing import List

class RewardsCog(commands.Cog, name="Rewards"):
    """Handles player rewards and playtime tracking."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_conan_players_updated(self, server_conf: dict, player_lines: List[str], rcon_client):
        """This event is dispatched by the StatusCog and triggers the reward logic."""
        await self.track_and_reward_players(server_conf, player_lines, rcon_client)

    async def track_and_reward_players(self, server_conf: dict, player_lines: List[str], rcon_client):
        reward_config = server_conf.get('REWARD_CONFIG', {})
        if not reward_config.get('ENABLED', False):
            return

        reward_intervals = reward_config.get('INTERVALS_MINUTES', {0: 120})
        server_name = server_conf["NAME"]
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

        if not online_players:
            return

        db_path = server_conf.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
        log_file_path = server_conf.get("LOG_FILE", "logs/rewards.log")

        try:
            with sqlite3.connect(db_path) as con:
                cur = con.cursor()

                # Finalize any pending registrations for online players
                for code, reg_data in list(pending_registrations.items()):
                    if 'char_name' in reg_data:
                        for player in online_players:
                            if player['char_name'] == reg_data['char_name']:
                                discord_id = reg_data['discord_id']
                                platform_id = player['platform_id']
                                
                                cur.execute("INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)", (platform_id, server_name))
                                cur.execute("UPDATE player_time SET discord_id = ? WHERE platform_id = ? AND server_name = ?", (discord_id, platform_id, server_name))
                                con.commit()

                                user = await self.bot.fetch_user(discord_id)
                                if user:
                                    await user.send(self.bot._("Sucesso! Sua conta do jogo '{char}' foi vinculada à sua conta do Discord.").format(char=player['char_name']))
                                logging.info(f"Successfully linked Discord user {discord_id} to character {player['char_name']} ({platform_id}).")
                                del pending_registrations[code]
                                break

                for player in online_players:
                    platform_id = player["platform_id"]
                    cur.execute("INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)", (platform_id, server_name))
                    cur.execute("UPDATE player_time SET online_minutes = online_minutes + 1 WHERE platform_id = ? AND server_name = ?", (platform_id, server_name))
                    cur.execute("SELECT online_minutes, last_rewarded_hour, discord_id, vip_level FROM player_time WHERE platform_id = ? AND server_name = ?", (platform_id, server_name))
                    result = cur.fetchone()
                    if not result or not result[2]:
                        continue

                    online_minutes, last_rewarded_hour, discord_id, vip_level = result
                    reward_interval = reward_intervals.get(vip_level, reward_intervals.get(0, 120))
                    current_hour_milestone = online_minutes // reward_interval

                    if current_hour_milestone > last_rewarded_hour:
                        # ... (rest of reward logic)
                        pass
        except Exception as e:
            logging.error(f"An error occurred in track_and_reward_players for server '{server_name}': {e}")

async def setup(bot):
    await bot.add_cog(RewardsCog(bot))
