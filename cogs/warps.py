from discord.ext import commands, tasks
from discord import app_commands
import logging
import re
from datetime import datetime, timedelta
import os
import discord

import config
from utils.database import (
    get_global_player_data,
    get_character_coordinates,
    save_player_home,
    get_player_home,
    DEFAULT_PLAYER_TRACKER_DB,
)
from utils.log_watcher import LogWatcher

# Constants
LOG_SCAN_INTERVAL_SECONDS = 5
LOG_LINES_TO_READ = 20
WARP_COMMAND_REGEX = re.compile(r"!warp\s+(\w+)")
WARP_LIST_REGEX = re.compile(r"!(warps|warplist)")
SETHOME_COMMAND_REGEX = re.compile(r"!sethome")
HOME_COMMAND_REGEX = re.compile(r"!home")
CHAT_CHARACTER_REGEX = re.compile(r"ChatWindow: Character (.+?) \(uid")


class WarpsCog(commands.Cog, name="Warps"):
    """Handles in-game warp commands."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        # Cooldown storage: {(char_name, server_name, command_type): expiration_datetime}
        self.cooldowns = {}
        # Watcher storage: {server_name: LogWatcher}
        self.watchers = {}
        self.process_warp_log_task.start()

    def cog_unload(self):
        """Clean up the cog before unloading."""
        self.process_warp_log_task.cancel()

    @app_commands.command(
        name="warps",
        description="Shows the list of available warp locations.",
    )
    async def warps_discord_command(self, interaction: discord.Interaction):
        """Slash command to show available warps."""
        embed = discord.Embed(
            title=self.bot._("📍 Warp Locations"),
            description=self.bot._(
                "These are the locations you can teleport to using `!warp <name>` in the in-game chat."
            ),
            color=discord.Color.blue(),
        )

        for server_conf in config.SERVERS:
            warp_config = server_conf.get("WARP_CONFIG")
            if warp_config and warp_config.get("ENABLED"):
                locations = warp_config.get("LOCATIONS", {})
                if locations:
                    loc_list = ", ".join([f"`{name}`" for name in locations.keys()])
                    embed.add_field(
                        name=server_conf["NAME"], value=loc_list, inline=False
                    )

        if not embed.fields:
            await interaction.response.send_message(
                self.bot._("No warps are currently configured."), ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(seconds=LOG_SCAN_INTERVAL_SECONDS)
    async def process_warp_log_task(self):
        """
        Periodically scans server logs for warp commands and processes them.
        """
        for server_conf in config.SERVERS:
            await self._process_log_for_server(server_conf)

    @process_warp_log_task.before_loop
    async def before_process_warp_log_task(self):
        """Waits for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()

    async def _process_log_for_server(self, server_conf: dict):
        """Processes the log file for a single server to find warp commands."""
        warp_config = server_conf.get("WARP_CONFIG")
        if not warp_config or not warp_config.get("ENABLED"):
            return

        log_path = server_conf.get("LOG_PATH")
        server_name = server_conf["NAME"]

        if not log_path:
            return

        if server_name not in self.watchers:
            self.watchers[server_name] = LogWatcher(log_path)

        new_lines = await self.watchers[server_name].read_new_lines()
        for line in new_lines:
            await self._process_log_line(line, server_conf, server_name)

    async def _process_log_line(self, line: str, server_conf: dict, server_name: str):
        """Parses a single log line for a warp command or list request."""
        char_match = CHAT_CHARACTER_REGEX.search(line)
        if not char_match:
            return

        char_name = char_match.group(1).strip()

        # 1. Check for Warp List Command (!warps / !warplist)
        if WARP_LIST_REGEX.search(line):
            await self._handle_list_request(char_name, server_conf)
            return

        # 2. Check for SetHome Command (!sethome)
        if SETHOME_COMMAND_REGEX.search(line):
            await self._handle_sethome(char_name, server_conf)
            return

        # 3. Check for Home Command (!home)
        if HOME_COMMAND_REGEX.search(line):
            await self._handle_home(char_name, server_conf)
            return

        # 4. Check for Warp Teleport Command (!warp <dest>)
        warp_match = WARP_COMMAND_REGEX.search(line)
        if warp_match:
            destination = warp_match.group(1).lower()
            await self._handle_warp(char_name, destination, server_conf, server_name)

    async def _get_player_info(self, rcon_client, char_name, server_name):
        """
        Fetches the player index (session ID) and platform ID for a character name.
        Returns: (idx, platform_id) or (None, None)
        """
        status_cog = self.bot.get_cog("Status")
        if not status_cog:
            return None, None

        try:
            response, _ = await status_cog.get_player_list(server_name)
            lines = response.split("\n")
            for line in lines:
                parts = line.split("|")
                # Format: ID | CharName | ... | PlatformID
                if len(parts) > 4:
                    current_name = parts[1].strip()
                    if current_name == char_name:
                        return parts[0].strip(), parts[4].strip()
        except Exception as e:
            logging.error(f"Error fetching player list for warp: {e}")
        return None, None

    async def _handle_list_request(self, char_name: str, server_conf: dict):
        """Sends the list of available warps to the player via Discord DM."""
        status_cog = self.bot.get_cog("Status")
        if not status_cog:
            return

        server_name = server_conf["NAME"]
        rcon_client = status_cog.rcon_clients.get(server_name)
        if not rcon_client:
            return

        _, platform_id = await self._get_player_info(
            rcon_client, char_name, server_name
        )
        if not platform_id:
            return

        player_data = get_global_player_data([platform_id])
        discord_id = player_data.get(platform_id, {}).get("discord_id")

        if discord_id:
            warp_config = server_conf.get("WARP_CONFIG", {})
            locations = warp_config.get("LOCATIONS", {})
            loc_names = ", ".join([f"`{name}`" for name in locations.keys()])

            msg = self.bot._(
                "📍 **Available Warps in {server}:**\n{locations}\n\nUse `!warp <name>` in the in-game chat."
            ).format(server=server_conf["NAME"], locations=loc_names)

            if warp_config.get("HOME_ENABLED"):
                msg += "\n\n" + self.bot._(
                    "🏠 **Home System:**\nUse `!sethome` to save your current position and `!home` to return."
                )

            try:
                user = await self.bot.fetch_user(discord_id)
                if user:
                    await user.send(msg)
            except:
                pass

    async def _handle_sethome(self, char_name: str, server_conf: dict):
        """Saves the current character position as their home."""
        warp_config = server_conf.get("WARP_CONFIG", {})
        if not warp_config.get("HOME_ENABLED"):
            return

        status_cog = self.bot.get_cog("Status")
        server_name = server_conf["NAME"]
        rcon_client = status_cog.rcon_clients.get(server_name) if status_cog else None
        if not rcon_client:
            return

        _, platform_id = await self._get_player_info(
            rcon_client, char_name, server_name
        )
        if not platform_id:
            return

        player_data = get_global_player_data([platform_id])
        discord_id = player_data.get(platform_id, {}).get("discord_id")

        if not discord_id:
            return

        # Check Cooldown for SetHome
        cooldown_minutes = warp_config.get("SETHOME_COOLDOWN_MINUTES", 5)
        now = datetime.now()
        cooldown_key = (char_name, server_name, "sethome")
        if cooldown_key in self.cooldowns:
            expiration = self.cooldowns[cooldown_key]
            if now < expiration:
                rem = int((expiration - now).total_seconds())
                logging.info(
                    f"Player {char_name} tried !sethome but is on cooldown ({rem}s remaining)."
                )
                try:
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(
                            self.bot._(
                                "⏳ **SetHome on Cooldown:** Please wait **{minutes}m {seconds}s**."
                            ).format(minutes=rem // 60, seconds=rem % 60)
                        )
                except:
                    pass
                return

        # Get coordinates from game.db
        game_db_path = server_conf.get("DB_PATH")
        coords = get_character_coordinates(game_db_path, char_name)

        if coords:
            x, y, z = coords
            player_db_path = server_conf.get(
                "PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB
            )
            if save_player_home(
                player_db_path, platform_id, server_conf["NAME"], x, y, z
            ):
                self.cooldowns[cooldown_key] = now + timedelta(minutes=cooldown_minutes)
                try:
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(
                            self.bot._(
                                "🏠 **Home Set!** Your location was saved in **{server}**.\n⚠️ *Note: There might be a slight difference in the exact position due to the server's automatic save cycle.*"
                            ).format(server=server_conf["NAME"])
                        )
                except:
                    pass
                logging.info(f"Player {char_name} set home at {x}, {y}, {z}")
        else:
            logging.warning(
                f"Could not find coordinates for {char_name} in {game_db_path}"
            )

    async def _handle_home(self, char_name: str, server_conf: dict):
        """Teleports the player to their saved home position."""
        warp_config = server_conf.get("WARP_CONFIG", {})
        if not warp_config.get("HOME_ENABLED"):
            return

        status_cog = self.bot.get_cog("Status")
        server_name = server_conf["NAME"]
        rcon_client = status_cog.rcon_clients.get(server_name) if status_cog else None
        if not rcon_client:
            return

        idx, platform_id = await self._get_player_info(
            rcon_client, char_name, server_name
        )
        if not idx or not platform_id:
            return

        player_data = get_global_player_data([platform_id])
        discord_id = player_data.get(platform_id, {}).get("discord_id")

        if not discord_id:
            return

        # Check Cooldown
        cooldown_minutes = warp_config.get("HOME_COOLDOWN_MINUTES", 15)
        now = datetime.now()
        cooldown_key = (char_name, server_name, "home")
        if cooldown_key in self.cooldowns:
            expiration = self.cooldowns[cooldown_key]
            if now < expiration:
                rem = int((expiration - now).total_seconds())
                logging.info(
                    f"Player {char_name} tried !home but is on cooldown ({rem}s remaining)."
                )
                try:
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(
                            self.bot._(
                                "⏳ **Home on Cooldown:** Please wait **{minutes}m {seconds}s**."
                            ).format(minutes=rem // 60, seconds=rem % 60)
                        )
                except:
                    pass
                return

        # Get home from DB
        player_db_path = server_conf.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
        home_coords = get_player_home(player_db_path, platform_id, server_name)

        if home_coords:
            x, y, z = home_coords
            try:
                # Use execute_safe_command for safe execution
                await status_cog.execute_safe_command(
                    server_name,
                    char_name,
                    lambda i: f"con {i} TeleportPlayer {x} {y} {z}",
                )

                logging.info(f"Teleported {char_name} to home")
                self.cooldowns[cooldown_key] = now + timedelta(minutes=cooldown_minutes)
                try:
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(
                            self.bot._(
                                "🏠 Welcome back to your home in **{server}**!"
                            ).format(server=server_name)
                        )
                except:
                    pass
            except Exception as e:
                logging.error(f"Home teleport error: {e}")
        else:
            try:
                user = await self.bot.fetch_user(discord_id)
                if user:
                    await user.send(
                        self.bot._(
                            "❌ **Error:** You haven't set a home yet. Use `!sethome` first."
                        )
                    )
            except:
                pass

    async def _handle_warp(
        self, char_name: str, destination: str, server_conf: dict, server_name: str
    ):
        """Validates and executes the warp."""
        warp_config = server_conf.get("WARP_CONFIG", {})
        locations = warp_config.get("LOCATIONS", {})

        if destination not in locations:
            return

        coords = locations[destination]
        cooldown_minutes = warp_config.get("COOLDOWN_MINUTES", 5)

        status_cog = self.bot.get_cog("Status")
        rcon_client = status_cog.rcon_clients.get(server_name) if status_cog else None
        if not rcon_client:
            return

        idx, platform_id = await self._get_player_info(
            rcon_client, char_name, server_name
        )
        if not idx or not platform_id:
            return

        player_data = get_global_player_data([platform_id])
        discord_id = player_data.get(platform_id, {}).get("discord_id")

        if not discord_id:
            logging.info(f"Player {char_name} not registered. Warp denied.")
            return

        # Check Cooldown
        now = datetime.now()
        cooldown_key = (char_name, server_name, "warp")
        if cooldown_key in self.cooldowns:
            expiration = self.cooldowns[cooldown_key]
            if now < expiration:
                rem = int((expiration - now).total_seconds())
                logging.info(
                    f"Player {char_name} tried !warp {destination} but is on cooldown ({rem}s remaining)."
                )
                try:
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(
                            self.bot._(
                                "⏳ **Warp on Cooldown:** Please wait **{minutes}m {seconds}s**."
                            ).format(minutes=rem // 60, seconds=rem % 60)
                        )
                except:
                    pass
                return

        try:
            # Use execute_safe_command for safe execution
            await status_cog.execute_safe_command(
                server_name, char_name, lambda i: f"con {i} TeleportPlayer {coords}"
            )

            logging.info(f"Teleported {char_name} to {destination}")
            self.cooldowns[cooldown_key] = now + timedelta(minutes=cooldown_minutes)
            try:
                user = await self.bot.fetch_user(discord_id)
                if user:
                    await user.send(
                        self.bot._(
                            "🚀 Teleported to **{destination}** in **{server}**!"
                        ).format(destination=destination, server=server_name)
                    )
            except:
                pass
        except Exception as e:
            logging.error(f"Warp error: {e}")


async def setup(bot):
    await bot.add_cog(WarpsCog(bot))
