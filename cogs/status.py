import asyncio
from discord.ext import commands, tasks
import discord
import logging
import re
import struct
from typing import Dict, List, Optional, Any, Tuple

from aiomcrcon import Client, RCONConnectionError

import config
from utils.database import (
    get_batch_player_levels,
    get_batch_player_data,
    get_global_player_data,
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
        self.rcon_locks: Dict[str, asyncio.Lock] = {}
        self.level_cache: Dict[str, int] = {} # Cache for player levels {char_name: level}
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
            server_name = server_conf["NAME"]
            self.rcon_clients[server_name] = Client(
                server_conf["SERVER_IP"],
                server_conf["RCON_PORT"],
                server_conf["RCON_PASS"],
            )
            self.rcon_locks[server_name] = asyncio.Lock()

    async def cog_unload(self):
        """
        Cleans up resources when the cog is unloaded.
        This method cancels the update task and closes all RCON connections.
        """
        self.update_all_statuses_task.cancel()
        for client in self.rcon_clients.values():
            await client.close()

    async def execute_rcon(self, server_name: str, command: str) -> Tuple[str, str]:
        """
        Executes an RCON command on the specified server with locking to prevent
        race conditions.
        """
        client = self.rcon_clients.get(server_name)
        lock = self.rcon_locks.get(server_name)

        if not client or not lock:
            raise ValueError(f"RCON client or lock not found for server: {server_name}")

        async with lock:
            try:
                await client.connect()
                return await client.send_cmd(command)
            except struct.error:
                # This happens when the server is starting up and sends an incomplete packet
                await client.close() # Force a clean state
                raise RCONConnectionError("Incomplete RCON packet received.")
            except asyncio.TimeoutError:
                # RCON connection timed out (server likely down or lagging heavily)
                await client.close()
                raise RCONConnectionError("RCON timed out.")
            except Exception as e:
                # If it's a connection error, aiomcrcon might need a clean state
                logging.warning(f"RCON execution failed for {server_name}: {e}")
                await client.close()
                raise e

    @tasks.loop(minutes=1)
    async def update_all_statuses_task(self):
        """
        The main task that periodically updates the status of all configured servers.
        This task runs every minute.
        """
        total_online_players = 0
        cluster_data = []
        server_statuses = []

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

            new_embed, player_count, server_data = await self._get_server_status_embed(
                server_conf, rcon_client
            )
            total_online_players += player_count
            await self._update_status_message(channel, new_embed)

            alias = server_conf.get("ALIAS", server_conf["NAME"])
            if server_data:
                cluster_data.append(server_data)
                fps = server_data["system_stats"].get("fps")
                server_statuses.append({"alias": alias, "online": True, "fps": fps})
            else:
                server_statuses.append({"alias": alias, "online": False, "fps": None})

        # Update consolidated cluster status if enabled
        if hasattr(config, "CLUSTER_STATUS") and config.CLUSTER_STATUS.get(
            "ENABLED", False
        ):
            await self._update_cluster_status(
                cluster_data, total_online_players, server_statuses
            )

        # WEB EXPORT: Generate status.json for the website
        await self._export_status_json(cluster_data, server_statuses)

        activity = discord.Game(
            name=self._("Players Online: {count}").format(count=total_online_players)
        )
        await self.bot.change_presence(activity=activity)

    async def _update_cluster_status(
        self,
        cluster_data: List[Dict[str, Any]],
        total_players: int,
        server_statuses: List[Dict[str, Any]],
    ):
        """
        Updates the consolidated cluster status message.

        Args:
            cluster_data: A list of dictionaries containing data for each online server.
            total_players: The total number of players online across all servers.
            server_statuses: A list of dictionaries with alias and online status for all servers.
        """
        channel_id = config.CLUSTER_STATUS.get("CHANNEL_ID")
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logging.error(f"Cluster status channel with ID {channel_id} not found.")
            return

        embed = discord.Embed(
            title=self._("🌍 Cluster Status"),
            description=self._("Consolidated status of all servers."),
            color=discord.Color.gold(),
        )

        all_players_details = []
        total_cpu = 0.0
        total_memory_gb = 0.0

        for server in cluster_data:
            server_name = server["name"]
            server_alias = server["alias"]
            online_players = server["online_players"]
            levels_map = server["levels_map"]
            player_data_map = server["player_data_map"]
            global_data_map = server.get("global_data_map", {})
            system_stats = server["system_stats"]

            # Aggregate System Stats
            if system_stats.get("cpu"):
                try:
                    cpu_val = float(system_stats["cpu"].replace("%", ""))
                    total_cpu += cpu_val
                except ValueError:
                    pass

            if system_stats.get("memory"):
                try:
                    mem_val = float(system_stats["memory"].replace(" GB", ""))
                    total_memory_gb += mem_val
                except ValueError:
                    pass

            # Format Player Details with Server Alias
            for player in online_players:
                level = levels_map.get(player["char_name"], 0)
                p_data = player_data_map.get(
                    player["platform_id"], {"online_minutes": 0, "is_registered": False}
                )
                
                # Registration status from global data
                is_registered = False
                if player["platform_id"] in global_data_map:
                    is_registered = bool(global_data_map[player["platform_id"]]["discord_id"])
                else:
                    is_registered = p_data["is_registered"]

                online_minutes = p_data["online_minutes"]

                p_hours, p_minutes = divmod(online_minutes, 60)
                playtime_str = f"{p_hours}h {p_minutes}m"

                detail_line = f"• {player['char_name']}"
                if level > 0:
                    detail_line += f" ({level})"
                detail_line += f" - {playtime_str} ({server_alias})"

                if is_registered:
                    detail_line += " ✅"
                else:
                    detail_line += " ❓"

                all_players_details.append(detail_line)

        if all_players_details:
            embed.add_field(
                name=self._("Online Players ({count})").format(count=total_players),
                value="\n".join(all_players_details),
                inline=False,
            )
        else:
            embed.add_field(
                name=self._("Online Players (0)"),
                value=self._("No one is playing at the moment."),
                inline=False,
            )

        # Server Status Field
        status_lines = []
        for s in server_statuses:
            icon = "✅" if s["online"] else "❌"
            fps_str = f" ({s['fps']} FPS)" if s.get("fps") else ""
            status_lines.append(f"{icon} {s['alias']}{fps_str}")

        if status_lines:
            embed.add_field(
                name=self._("Servers"),
                value="\n".join(status_lines),
                inline=False,
            )

        embed.add_field(
            name=self._("Total CPU"), value=f"{total_cpu:.1f}%", inline=True
        )
        embed.add_field(
            name=self._("Total Memory"), value=f"{total_memory_gb:.2f} GB", inline=True
        )

        embed.set_footer(text=self._("Cluster status updated"))
        embed.timestamp = discord.utils.utcnow()

        await self._update_status_message(channel, embed)

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

    async def _export_status_json(self, cluster_data, server_statuses):
        """Exports the current cluster status to a JSON file for web usage."""
        import json
        import os
        from datetime import datetime

        export_data = {
            "last_updated": datetime.now().isoformat(),
            "total_players": sum(len(s["online_players"]) for s in cluster_data),
            "servers": []
        }

        # Create a map for quick lookup of online status
        status_map = {s["alias"]: s["online"] for s in server_statuses}

        # Process each server
        for s in cluster_data:
            online_players = []
            for p in s["online_players"]:
                level = s["levels_map"].get(p["char_name"], 0)
                p_data = s["player_data_map"].get(p["platform_id"], {"online_minutes": 0})
                
                online_players.append({
                    "char_name": p["char_name"],
                    "level": level,
                    "playtime_minutes": p_data["online_minutes"]
                })

            export_data["servers"].append({
                "name": s["name"],
                "alias": s["alias"],
                "online": status_map.get(s["alias"], False),
                "players_count": len(online_players),
                "players": online_players,
                "stats": s["system_stats"]
            })

        # Ensure output directory exists
        output_path = os.path.join("output", "status.json")
        os.makedirs("output", exist_ok=True)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to export status.json: {e}")

    @update_all_statuses_task.before_loop
    async def before_update_all_statuses_task(self):
        """
        Prepares the cog before the main update loop starts.
        This method waits for the bot to be ready, initializes the RCON clients,
        and finds any existing status messages to edit.
        """
        await self.bot.wait_until_ready()
        await self.async_init()  # Initialize RCON clients
        
        # 1. Find messages for individual servers
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
        
        # 2. Find message for Cluster Status
        if hasattr(config, "CLUSTER_STATUS") and config.CLUSTER_STATUS.get("ENABLED"):
            cluster_channel_id = config.CLUSTER_STATUS.get("CHANNEL_ID")
            cluster_channel = self.bot.get_channel(cluster_channel_id)
            if cluster_channel:
                async for msg in cluster_channel.history(limit=50):
                    if (
                        msg.author.id == self.bot.user.id
                        and msg.embeds
                        and (msg.embeds[0].title == self._("🌍 Cluster Status") or "Cluster" in msg.embeds[0].title)
                    ):
                        self.status_messages[cluster_channel_id] = msg
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
            response, _ = await self.execute_rcon(server_name, "ListPlayers")
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
        player_data_map: Dict[str, Dict[str, Any]],
        global_data_map: Dict[str, Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Formats the details of each online player into a list of strings.

        Args:
            online_players: A list of dictionaries representing the online players.
            levels_map: A dictionary mapping character names to their levels.
            player_data_map: A dictionary mapping platform IDs to their data.
            global_data_map: A dictionary mapping platform IDs to global data.

        Returns:
            A list of strings, where each string is a formatted line of player details.
        """
        player_details = []
        for player in online_players:
            level = levels_map.get(player["char_name"], 0)
            p_data = player_data_map.get(
                player["platform_id"], {"online_minutes": 0, "is_registered": False}
            )
            
            # Registration status comes from global data now
            is_registered = False
            if global_data_map and player["platform_id"] in global_data_map:
                is_registered = bool(global_data_map[player["platform_id"]]["discord_id"])
            else:
                is_registered = p_data["is_registered"] # Fallback

            online_minutes = p_data["online_minutes"]

            p_hours, p_minutes = divmod(online_minutes, 60)
            playtime_str = f"{p_hours}h {p_minutes}m"
            detail_line = f"• {player['char_name']}"
            if level > 0:
                detail_line += f" ({level})"
            detail_line += f" - {playtime_str}"

            if is_registered:
                detail_line += " ✅"
            else:
                detail_line += " ❓"

            player_details.append(detail_line)
        return player_details

    async def _get_server_status_embed(
        self, server_config: dict, rcon_client: Client
    ) -> Tuple[discord.Embed, int, Optional[Dict[str, Any]]]:
        """
        Creates the embed for the server status, showing online players and server stats.

        Args:
            server_config: The configuration for the server.
            rcon_client: The RCON client for the server.

        Returns:
            A tuple containing the discord.Embed object, the count of online players,
            and a dictionary with server data (or None if offline).
        """
        server_name = server_config["NAME"]
        player_lines = await self._get_player_lines(rcon_client, server_name)

        if player_lines is None:
            return self._create_offline_embed(server_config), 0, None

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

        server_data = {
            "name": server_name,
            "alias": server_config.get("ALIAS", server_name),
            "online_players": online_players,
            "system_stats": system_stats,
            "levels_map": {},
            "player_data_map": {},
        }

        if online_players:
            char_names = [p["char_name"] for p in online_players]
            platform_ids = [p["platform_id"] for p in online_players]
            
            # Try to get fresh levels
            levels_data = get_batch_player_levels(
                server_config.get("DB_PATH"), char_names
            )
            
            if levels_data is not None:
                # Update cache with new data
                for char, lvl in levels_data.items():
                    self.level_cache[char] = lvl
                levels_map = levels_data
            else:
                # DB Error: Use cached levels
                levels_map = {name: self.level_cache.get(name, 0) for name in char_names}
                logging.warning(f"Using cached levels for {server_name} due to DB read error.")

            player_data_map = get_batch_player_data(
                server_config.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB),
                platform_ids,
                server_name,
            )
            global_data_map = get_global_player_data(platform_ids)

            server_data["levels_map"] = levels_map
            server_data["player_data_map"] = player_data_map
            server_data["global_data_map"] = global_data_map

            player_details = self._format_player_details(
                online_players, levels_map, player_data_map, global_data_map
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
        return embed, len(online_players), server_data

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
