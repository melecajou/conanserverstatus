import config
from utils.database import DEFAULT_PLAYER_TRACKER_DB
from discord.ext import commands
import logging
import sqlite3
from typing import List
from bot import pending_registrations

class RewardsCog(commands.Cog, name="Rewards"):
    """Handles player rewards and playtime tracking."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._

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
        online_minutes = 0

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
                                
                                # This is the crucial part: UPDATE the existing row.
                                cur.execute("UPDATE player_time SET discord_id = ? WHERE platform_id = ? AND server_name = ?", (str(discord_id), platform_id, server_name))
                                con.commit()

                                user = await self.bot.fetch_user(discord_id)
                                if user:
                                    await user.send(self.bot._("Sucesso! Sua conta do jogo '{char}' foi vinculada à sua conta do Discord.").format(char=player['char_name']))
                                logging.info(f"Successfully linked Discord user {discord_id} to character {player['char_name']} ({platform_id}).")
                                del pending_registrations[code]
                                break # Move to the next pending registration

                for player in online_players:
                    platform_id = player["platform_id"]
                    cur.execute("INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)", (platform_id, server_name))

                    cur.execute("UPDATE player_time SET online_minutes = online_minutes + 1 WHERE platform_id = ? AND server_name = ?", (platform_id, server_name))


                    # Check for reward
                    cur.execute("SELECT online_minutes, last_rewarded_hour, discord_id, vip_level FROM player_time WHERE platform_id = ? AND server_name = ?", (platform_id, server_name))
                    result = cur.fetchone()

                    if not result or result[2] is None or result[2] == '': # Skip if no record or not linked

                        continue
                    online_minutes, last_rewarded_hour, discord_id, vip_level = result
                    
                    # Get the correct reward interval based on VIP level
                    reward_interval = reward_intervals.get(vip_level, reward_intervals.get(0, 120))
        
                    current_hour_milestone = online_minutes // reward_interval
        

                    if current_hour_milestone > last_rewarded_hour:
                        # Calculate the actual hours played for the log message
                        total_hours_played = current_hour_milestone * (reward_interval / 60.0)
                        logging.info(self._(f"Player {player['char_name']} on server '{server_name}' reached a new reward milestone at {total_hours_played:.1f} hours. Issuing reward."))
                        
                        item_id = reward_config["REWARD_ITEM_ID"]
                        quantity = reward_config["REWARD_QUANTITY"]
                        command = f"con {player['idx']} SpawnItem {item_id} {quantity}"
                        
                        try:
                            response, _unused = await rcon_client.send_cmd(command)
                            logging.info(self._(f"Reward command '{command}' for player {player['char_name']} on server '{server_name}' executed. Response: {response.strip()}"))
                            
                            # Log the reward to the text file
                            # log_reward_to_file(
                            #     log_file_path,
                            #     server_name,
                            #     player['char_name'],
                            #     online_minutes,
                            #     item_id,
                            #     quantity
                            # )

                            # Update rewarded hour in DB
                            cur.execute("UPDATE player_time SET last_rewarded_hour = ? WHERE platform_id = ? AND server_name = ?", (current_hour_milestone, platform_id, server_name))

                        except Exception as e:
                            logging.error(self._(f"Failed to send reward RCON command for player {player['char_name']} on server '{server_name}': {e}"))
        except Exception as e:
            logging.error(f"An error occurred in track_and_reward_players for server '{server_name}': {e}")
        finally:
            if rcon_client:
                await rcon_client.close()

async def setup(bot):
    await bot.add_cog(RewardsCog(bot))
