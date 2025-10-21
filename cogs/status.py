from discord.ext import commands, tasks
import discord
import logging
from typing import Dict, List, Optional

from aiomcrcon import Client

import config
from utils.database import get_batch_player_levels, get_batch_online_times, DEFAULT_PLAYER_TRACKER_DB
from utils.log_parser import parse_server_log
from utils.rcon import attempt_rcon_connection

class StatusCog(commands.Cog, name="Status"):
    """Handles the live status updates for all servers."""

    def __init__(self, bot):
        self.bot = bot
        self.status_messages: Dict[int, discord.Message] = {}
        if not self.update_all_statuses_task.is_running():
            self.update_all_statuses_task.start()

    def cog_unload(self):
        self.update_all_statuses_task.cancel()

    @tasks.loop(minutes=1)
    async def update_all_statuses_task(self):
        logging.info("STATUS_DEBUG: Starting status update task loop.")
        for server_conf in config.SERVERS:
            if not server_conf.get("ENABLED", True):
                continue

            channel_id = server_conf["STATUS_CHANNEL_ID"]
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logging.error(f"Channel with ID {channel_id} for '{server_conf['NAME']}' not found.")
                continue

            logging.info(f"STATUS_DEBUG: Processing server: {server_conf['NAME']}")

            new_embed = None
            rcon_client = await attempt_rcon_connection(server_conf)
            logging.info(f"STATUS_DEBUG: RCON connection attempt for {server_conf['NAME']} completed. Client: {'OK' if rcon_client else 'Failed'}")

            if rcon_client:
                try:
                    logging.info(f"STATUS_DEBUG: Calling get_server_status_embed for {server_conf['NAME']}.")
                    new_embed = await self.get_server_status_embed(server_conf, rcon_client)
                    logging.info(f"STATUS_DEBUG: get_server_status_embed for {server_conf['NAME']} finished. Embed created: {'Yes' if new_embed else 'No'}")
                except Exception as e:
                    logging.error(f"Failed to generate status embed for '{server_conf['NAME']}'", exc_info=True)
                finally:
                    await rcon_client.close()
            
            if not new_embed:
                new_embed = self.create_offline_embed(server_conf)
                logging.info(f"STATUS_DEBUG: Created offline embed for {server_conf['NAME']}.")

            try:
                status_message = self.status_messages.get(channel_id)
                if status_message:
                    logging.info(f"STATUS_DEBUG: Attempting to edit message {status_message.id} in channel {channel_id} for {server_conf['NAME']}.")
                    await status_message.edit(embed=new_embed)
                    logging.info(f"STATUS_DEBUG: Successfully edited message for {server_conf['NAME']}.")
                else:
                    logging.info(f"STATUS_DEBUG: No existing message found for {server_conf['NAME']}. Attempting to send a new one.")
                    new_msg = await channel.send(embed=new_embed)
                    self.status_messages[channel_id] = new_msg
                    logging.info(f"STATUS_DEBUG: Successfully sent new message {new_msg.id} for {server_conf['NAME']}.")
            except discord.errors.NotFound:
                logging.warning(f"Message for '{server_conf['NAME']}' not found. Creating a new one.")
                new_msg = await channel.send(embed=new_embed)
                self.status_messages[channel_id] = new_msg
            except Exception as e:
                logging.error(f"Error updating status message for '{server_conf['NAME']}': {e}")
                if channel_id in self.status_messages:
                    del self.status_messages[channel_id]



    async def get_server_status_embed(self, server_config: dict, rcon_client: Client) -> Optional[discord.Embed]:
        server_name = server_config["NAME"]
        game_db_path = server_config.get("DB_PATH")
        player_db_path = server_config.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
        log_path = server_config.get("LOG_PATH")

        response, _unused = await rcon_client.send_cmd("ListPlayers")
        player_lines = response.split('\n')[1:]

        # This cog is only for status, so we trigger the rewards cog to do its work.
        # The bot will dispatch this event, and the RewardsCog will pick it up.
        self.bot.dispatch("conan_players_updated", server_config, player_lines, rcon_client)

        system_stats = parse_server_log(log_path)

        online_players = []
        for line in player_lines:
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) > 4:
                online_players.append({
                    "char_name": parts[1].strip(),
                    "platform_id": parts[4].strip()
                })

        embed = discord.Embed(title=f"✅ {server_name}", description=self.bot._("The server is operating normally."), color=discord.Color.green())

        if online_players:
            char_names = [p['char_name'] for p in online_players]
            platform_ids = [p['platform_id'] for p in online_players]
            levels_map = get_batch_player_levels(game_db_path, char_names)
            times_map = get_batch_online_times(player_db_path, platform_ids, server_name)

            player_details = []
            for player in online_players:
                level = levels_map.get(player["char_name"], 0)
                online_minutes = times_map.get(player["platform_id"], 0)
                p_hours, p_minutes = divmod(online_minutes, 60)
                playtime_str = f"{p_hours}h {p_minutes}m"
                detail_line = f"• {player['char_name']}"
                if level > 0:
                    detail_line += f" ({level})"
                detail_line += f" - {playtime_str}"
                player_details.append(detail_line)
            embed.add_field(name=self.bot._("Online Players ({count})").format(count=len(online_players)), value="\n".join(player_details), inline=False)
        else:
            embed.add_field(name=self.bot._("Online Players (0)"), value=self.bot._("No one is playing at the moment."), inline=False)

        if system_stats.get('uptime'):
            embed.add_field(name=self.bot._("Uptime"), value=system_stats['uptime'], inline=True)
        if system_stats.get('fps'):
            embed.add_field(name=self.bot._("Server FPS"), value=system_stats['fps'], inline=True)
        if system_stats.get('memory'):
            embed.add_field(name=self.bot._("Memory"), value=system_stats['memory'], inline=True)
        if system_stats.get('cpu'):
            embed.add_field(name=self.bot._("CPU"), value=system_stats['cpu'], inline=True)

        footer_text = self.bot._("Status updated")
        if system_stats.get('version'):
            footer_text += f" | Version: {system_stats['version']}"
        embed.set_footer(text=footer_text)
        embed.timestamp = discord.utils.utcnow()
        return embed

    def create_offline_embed(self, server_conf: dict) -> discord.Embed:
        embed = discord.Embed(title=f"❌ {server_conf['NAME']}", description=self.bot._("Could not connect to the server. It may be offline or restarting."), color=discord.Color.red())
        embed.set_footer(text=self.bot._("Check the console or contact an administrator."))
        embed.timestamp = discord.utils.utcnow()
        return embed

async def setup(bot):
    await bot.add_cog(StatusCog(bot))