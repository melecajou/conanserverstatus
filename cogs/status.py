from discord.ext import commands, tasks
import discord
import logging
from typing import Dict, List, Optional, Any, Tuple

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
        """
        Asynchronously initializes the RCON clients for each server.
        This method is called before the main update loop starts.
        """
        for server_conf in config.SERVERS:
            if not server_conf.get("ENABLED", True):
                continue
            self.rcon_clients[server_conf["NAME"]] = Client(
                server_conf["SERVER_IP"],
                server_conf["RCON_PORT"],
                server_conf["RCON_PASS"],
            )

    async def cog_unload(self):
        """
        Cleans up resources when the cog is unloaded.
        This method cancels the update task and closes all RCON connections.
        """
        self.update_all_statuses_task.cancel()
        for client in self.rcon_clients.values():
            await client.close()

    @tasks.loop(minutes=1)
    async def update_all_statuses_task(self):
        """
        The main task that periodically updates the status of all configured servers.
        This task runs every minute.
        """
        total_online_players = 0
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

            new_embed, player_count = await self._get_server_status_embed(
                server_conf, rcon_client
            )
            total_online_players += player_count
            await self._update_status_message(channel, new_embed)

        activity = discord.Game(
            name=self._("Players Online: {count}").format(count=total_online_players)
        )
        await self.bot.change_presence(activity=activity)

    async def _update_status_message(
        self, channel: discord.TextChannel, embed: discord.Embed
    ):
        """
        Updates the status message in the given channel with the new embed.
        If a message already exists, it will be edited. Otherwise, a new message will be sent.

        Args:
            channel: The channel where the status message is located.
            embed: The new embed to display.
        """
        try:
            status_message = self.status_messages.get(channel.id)
            if status_message:
                await status_message.edit(embed=embed)
            else:
                new_msg = await channel.send(embed=embed)
                self.status_messages[channel.id] = new_msg
        except discord.errors.NotFound:
            logging.warning(
                f"Message in channel '{channel.name}' not found. Creating a new one."
            )
            new_msg = await channel.send(embed=embed)
            self.status_messages[channel.id] = new_msg
        except Exception as e:
            logging.error(f"Error updating status message in '{channel.name}': {e}")
            if channel.id in self.status_messages:
                del self.status_messages[channel.id]

    @update_all_statuses_task.before_loop
    async def before_update_all_statuses_task(self):
        """
        Prepares the cog before the main update loop starts.
        This method waits for the bot to be ready, initializes the RCON clients,
        and finds any existing status messages to edit.
        """
        await self.bot.wait_until_ready()
        await self.async_init()  # Initialize RCON clients
        for server_conf in config.SERVERS:
            if not server_conf.get("ENABLED", True):
                continue
            channel_id = server_conf["STATUS_CHANNEL_ID"]
            channel = self.bot.get_channel(channel_id)
            if channel:
                # Look for the last message sent by the bot with a status embed
                async for msg in channel.history(limit=50):
                    if (
                        msg.author.id == self.bot.user.id
                        and msg.embeds
                        and msg.embeds[0].title.startswith(("✅", "❌"))
                    ):
                        self.status_messages[channel_id] = msg
                        break

    async def _get_player_lines(
        self, rcon_client: Client, server_name: str
    ) -> Optional[List[str]]:
        """
        Retrieves the list of online players from the server using an RCON command.

        Args:
            rcon_client: The RCON client for the server.
            server_name: The name of the server.

        Returns:
            A list of strings, where each string represents a line of player data,
            or None if the connection fails.
        """
        try:
            await rcon_client.connect()
            response, _ = await rcon_client.send_cmd("ListPlayers")
            return [
                line
                for line in response.split("\n")
                if line.strip().startswith(tuple("0123456789"))
            ]
        except RCONConnectionError as e:
            logging.warning(f"RCON connection failed for {server_name}: {e}")
            return None
        except Exception as e:
            logging.error(
                f"An unexpected error occurred while getting player lines for '{server_name}': {e}",
                exc_info=True,
            )
            return None

    def _format_player_details(
        self,
        online_players: List[Dict[str, Any]],
        levels_map: Dict[str, int],
        times_map: Dict[str, int],
    ) -> List[str]:
        """
        Formats the details of each online player into a list of strings.

        Args:
            online_players: A list of dictionaries representing the online players.
            levels_map: A dictionary mapping character names to their levels.
            times_map: A dictionary mapping platform IDs to their online minutes.

        Returns:
            A list of strings, where each string is a formatted line of player details.
        """
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
        return player_details

    async def _get_server_status_embed(
        self, server_config: dict, rcon_client: Client
    ) -> Tuple[discord.Embed, int]:
        """
        Creates the embed for the server status, showing online players and server stats.

        Args:
            server_config: The configuration for the server.
            rcon_client: The RCON client for the server.

        Returns:
            A tuple containing the discord.Embed object and the count of online players.
        """
        server_name = server_config["NAME"]
        player_lines = await self._get_player_lines(rcon_client, server_name)

        if player_lines is None:
            return self._create_offline_embed(server_config), 0

        # Dispatch an event with the raw player lines for other cogs to use
        self.bot.dispatch(
            "conan_players_updated", server_config, player_lines, rcon_client
        )

        system_stats = parse_server_log(server_config.get("LOG_PATH"))
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
            levels_map = get_batch_player_levels(
                server_config.get("DB_PATH"), char_names
            )
            times_map = get_batch_online_times(
                server_config.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB),
                platform_ids,
                server_name,
            )
            player_details = self._format_player_details(
                online_players, levels_map, times_map
            )
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

        # Add system stats to the embed if available
        for key, name in [
            ("uptime", "Uptime"),
            ("fps", "Server FPS"),
            ("memory", "Memory"),
            ("cpu", "CPU"),
        ]:
            if system_stats.get(key):
                embed.add_field(name=self._(name), value=system_stats[key], inline=True)

        footer_text = self._("Status updated")
        if system_stats.get("version"):
            footer_text += f" | Version: {system_stats['version']}"
        embed.set_footer(text=footer_text)
        embed.timestamp = discord.utils.utcnow()
        return embed, len(online_players)

    def _create_offline_embed(self, server_conf: dict) -> discord.Embed:
        """
        Creates an embed to indicate that a server is offline.

        Args:
            server_conf: The configuration for the server.

        Returns:
            A discord.Embed object with a red color and an offline message.
        """
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
