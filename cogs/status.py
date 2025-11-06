from discord.ext import commands, tasks
import discord
import logging
from typing import Dict, List, Optional

from aiomcrcon import Client, RCONConnectionError

import config
from utils.database import (
    get_batch_player_levels,
    get_batch_online_times,
    DEFAULT_PLAYER_TRACKER_DB,
)
from utils.log_parser import parse_server_log


class StatusCog(commands.Cog, name="Status"):
    """Handles the live status updates for all servers."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.status_messages: Dict[int, discord.Message] = {}
        self.rcon_clients: Dict[str, Client] = {}
        if not self.update_all_statuses_task.is_running():
            self.update_all_statuses_task.start()

    async def async_init(self):
        """Asynchronous initialization for the cog."""
        for server_conf in config.SERVERS:
            if not server_conf.get("ENABLED", True):
                continue
            self.rcon_clients[server_conf["NAME"]] = Client(
                server_conf["SERVER_IP"],
                server_conf["RCON_PORT"],
                server_conf["RCON_PASS"],
            )

    async def cog_unload(self):
        self.update_all_statuses_task.cancel()
        for client in self.rcon_clients.values():
            await client.close()

    @tasks.loop(minutes=1)
    async def update_all_statuses_task(self):
        for server_conf in config.SERVERS:
            if not server_conf.get("ENABLED", True):
                continue

            channel_id = server_conf["STATUS_CHANNEL_ID"]
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logging.error(
                    f"Channel with ID {channel_id} for '{server_conf['NAME']}' not found."
                )
                continue

            rcon_client = self.rcon_clients.get(server_conf["NAME"])
            if not rcon_client:
                logging.error(
                    f"RCON client not initialized for {server_conf['NAME']}. Skipping."
                )
                continue

            new_embed = await self.get_server_status_embed(server_conf, rcon_client)

            try:
                status_message = self.status_messages.get(channel_id)
                if status_message:
                    await status_message.edit(embed=new_embed)
                else:
                    new_msg = await channel.send(embed=new_embed)
                    self.status_messages[channel_id] = new_msg
            except discord.errors.NotFound:
                logging.warning(
                    f"Message for '{server_conf['NAME']}' not found. Creating a new one."
                )
                new_msg = await channel.send(embed=new_embed)
                self.status_messages[channel_id] = new_msg
            except Exception as e:
                logging.error(
                    f"Error updating status message for '{server_conf['NAME']}': {e}"
                )
                if channel_id in self.status_messages:
                    del self.status_messages[channel_id]

    @update_all_statuses_task.before_loop
    async def before_update_all_statuses_task(self):
        await self.bot.wait_until_ready()
        await self.async_init()  # Initialize RCON clients
        for server_conf in config.SERVERS:
            if not server_conf.get("ENABLED", True):
                continue
            channel_id = server_conf["STATUS_CHANNEL_ID"]
            channel = self.bot.get_channel(channel_id)
            if channel:
                async for msg in channel.history(limit=50):
                    if (
                        msg.author.id == self.bot.user.id
                        and msg.embeds
                        and msg.embeds[0].title.startswith("✅")
                    ):
                        self.status_messages[channel_id] = msg
                        break

    async def get_server_status_embed(
        self, server_config: dict, rcon_client: Client
    ) -> discord.Embed:
        server_name = server_config["NAME"]
        game_db_path = server_config.get("DB_PATH")
        player_db_path = server_config.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
        log_path = server_config.get("LOG_PATH")

        try:
            await rcon_client.connect()
            response, _ = await rcon_client.send_cmd("ListPlayers")
            player_lines = [
                line
                for line in response.split("\n")
                if line.strip().startswith(tuple("0123456789"))
            ]
            self.bot.dispatch(
                "conan_players_updated", server_config, player_lines, rcon_client
            )
        except RCONConnectionError as e:
            logging.warning(f"RCON connection failed for {server_name}: {e}")
            return self.create_offline_embed(server_config)
        except Exception as e:
            logging.error(
                f"An unexpected error occurred for '{server_name}': {e}", exc_info=True
            )
            return self.create_offline_embed(server_config)

        system_stats = parse_server_log(log_path)
        online_players = []
        for line in player_lines:
            parts = line.split("|")
            if len(parts) > 4:
                online_players.append(
                    {"char_name": parts[1].strip(), "platform_id": parts[4].strip()}
                )

        embed = discord.Embed(
            title=f"✅ {server_name}",
            description=self._("The server is operating normally."),
            color=discord.Color.green(),
        )

        if online_players:
            char_names = [p["char_name"] for p in online_players]
            platform_ids = [p["platform_id"] for p in online_players]
            levels_map = get_batch_player_levels(game_db_path, char_names)
            times_map = get_batch_online_times(
                player_db_path, platform_ids, server_name
            )

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
            embed.add_field(
                name=self._("Online Players ({count})").format(
                    count=len(online_players)
                ),
                value="\n".join(player_details),
                inline=False,
            )
        else:
            embed.add_field(
                name=self._("Online Players (0)"),
                value=self._("No one is playing at the moment."),
                inline=False,
            )

        if system_stats.get("uptime"):
            embed.add_field(
                name=self._("Uptime"), value=system_stats["uptime"], inline=True
            )
        if system_stats.get("fps"):
            embed.add_field(
                name=self._("Server FPS"), value=system_stats["fps"], inline=True
            )
        if system_stats.get("memory"):
            embed.add_field(
                name=self._("Memory"), value=system_stats["memory"], inline=True
            )
        if system_stats.get("cpu"):
            embed.add_field(name=self._("CPU"), value=system_stats["cpu"], inline=True)

        footer_text = self._("Status updated")
        if system_stats.get("version"):
            footer_text += f" | Version: {system_stats['version']}"
        embed.set_footer(text=footer_text)
        embed.timestamp = discord.utils.utcnow()
        return embed

    def create_offline_embed(self, server_conf: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"❌ {server_conf['NAME']}",
            description=self._(
                "Could not connect to the server. It may be offline or restarting."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text=self._("Check the console or contact an administrator."))
        embed.timestamp = discord.utils.utcnow()
        return embed


async def setup(bot):
    cog = StatusCog(bot)
    await bot.add_cog(cog)
