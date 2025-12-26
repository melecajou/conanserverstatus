from discord.ext import commands, tasks
import logging
import re
from datetime import datetime, timedelta
import os
import discord

import config
from utils.database import get_global_player_data

# Constants
LOG_SCAN_INTERVAL_SECONDS = 5
LOG_LINES_TO_READ = 20
WARP_COMMAND_REGEX = re.compile(r"!warp (\w+)")
CHAT_CHARACTER_REGEX = re.compile(r"ChatWindow: Character (.+?) \(uid")


class WarpsCog(commands.Cog, name="Warps"):
    """Handles in-game warp commands."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        # Cooldown storage: {(char_name, server_name): expiration_datetime}
        self.cooldowns = {}
        # Simple cache to prevent double execution: {(char_name, destination, line_content_hash): expiration_time}
        self.processed_commands = set() 
        self.process_warp_log_task.start()

    def cog_unload(self):
        """Clean up the cog before unloading."""
        self.process_warp_log_task.cancel()

    @tasks.loop(seconds=LOG_SCAN_INTERVAL_SECONDS)
    async def process_warp_log_task(self):
        """
        Periodically scans server logs for warp commands and processes them.
        """
        self._cleanup_processed_cache()
        for server_conf in config.SERVERS:
            await self._process_log_for_server(server_conf)

    @process_warp_log_task.before_loop
    async def before_process_warp_log_task(self):
        """Waits for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()

    def _cleanup_processed_cache(self):
        """Removes old entries from the processed commands cache."""
        now = datetime.now()
        # Keep entries for 1 minute
        self.processed_commands = {
            entry for entry in self.processed_commands 
            if entry[3] > now
        }
        
        # Also clean up cooldowns that have expired
        keys_to_remove = [k for k, v in self.cooldowns.items() if v < now]
        for k in keys_to_remove:
            del self.cooldowns[k]

    async def _process_log_for_server(self, server_conf: dict):
        """Processes the log file for a single server to find warp commands."""
        warp_config = server_conf.get("WARP_CONFIG")
        if not warp_config or not warp_config.get("ENABLED"):
            return

        log_path = server_conf.get("LOG_PATH")
        server_name = server_conf["NAME"]

        if not log_path or not os.path.exists(log_path):
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                # Read last lines
                lines = f.readlines()[-LOG_LINES_TO_READ:]
                for line in lines:
                    await self._process_log_line(line, server_conf, server_name)
        except Exception as e:
            logging.error(f"Error processing warp log for server {server_name}: {e}")

    async def _process_log_line(self, line: str, server_conf: dict, server_name: str):
        """Parses a single log line for a warp command and processes it."""
        if "!warp" not in line:
            return

        warp_match = WARP_COMMAND_REGEX.search(line)
        if not warp_match:
            return

        destination = warp_match.group(1).lower()
        
        char_match = CHAT_CHARACTER_REGEX.search(line)
        if not char_match:
            return
            
        char_name = char_match.group(1).strip()

        # Generate a unique hash for this command instance to prevent duplicates
        line_hash = hash(line)
        cache_key = (char_name, destination, line_hash, datetime.now() + timedelta(minutes=1))
        
        # Check if already processed
        if any(entry[0] == char_name and entry[1] == destination and entry[2] == line_hash for entry in self.processed_commands):
            return

        self.processed_commands.add(cache_key)

        await self._handle_warp(char_name, destination, server_conf, server_name)

    async def _get_player_info(self, rcon_client, char_name):
        """
        Fetches the player index (session ID) and platform ID for a character name.
        Returns: (idx, platform_id) or (None, None)
        """
        try:
            response, _ = await rcon_client.send_cmd("ListPlayers")
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

    async def _handle_warp(self, char_name: str, destination: str, server_conf: dict, server_name: str):
        """Validates and executes the warp."""
        warp_config = server_conf.get("WARP_CONFIG", {})
        locations = warp_config.get("LOCATIONS", {})
        
        # Check if location exists
        if destination not in locations:
            logging.info(f"Player {char_name} tried invalid warp location: {destination}")
            return

        coords = locations[destination]
        cooldown_minutes = warp_config.get("COOLDOWN_MINUTES", 5)

        # Execute Teleport
        status_cog = self.bot.get_cog("Status")
        if not status_cog:
            logging.error("StatusCog not found. Cannot execute warp.")
            return

        rcon_client = status_cog.rcon_clients.get(server_name)
        if not rcon_client:
            logging.error(f"RCON client not found for {server_name}")
            return

        # Fetch Player Info
        idx, platform_id = await self._get_player_info(rcon_client, char_name)
        if not idx or not platform_id:
            logging.warning(f"Could not find session ID/Platform ID for player {char_name}. Teleport aborted.")
            return

        # Check Registration (Global DB)
        player_data = get_global_player_data([platform_id])
        discord_id = player_data.get(platform_id, {}).get("discord_id")

        if not discord_id:
            logging.info(f"Player {char_name} ({platform_id}) tried to warp but is not registered.")
            return

        # Check Cooldown
        now = datetime.now()
        cooldown_key = (char_name, server_name)
        if cooldown_key in self.cooldowns:
            expiration = self.cooldowns[cooldown_key]
            if now < expiration:
                remaining_seconds = int((expiration - now).total_seconds())
                minutes, seconds = divmod(remaining_seconds, 60)
                logging.info(f"Player {char_name} warp ignored (cooldown: {minutes}m {seconds}s remaining).")
                try:
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        await user.send(f"⏳ **Warp em Cooldown:** Aguarde mais **{minutes}m {seconds}s** para usar o teleporte novamente.")
                except: pass
                return

        # Command: con <ID> TeleportPlayer <X> <Y> <Z>
        teleport_cmd = f"con {idx} TeleportPlayer {coords}"
        
        try:
            await rcon_client.send_cmd(teleport_cmd)
            logging.info(f"Teleported {char_name} (ID: {idx}) to {destination} on {server_name}")
            
            # Set Cooldown
            self.cooldowns[cooldown_key] = now + timedelta(minutes=cooldown_minutes)

            # Send DM Feedback
            try:
                user = await self.bot.fetch_user(discord_id)
                if user:
                    await user.send(f"🚀 **Conan Warp:** Você foi teleportado para **{destination}** no servidor **{server_name}**!")
            except discord.Forbidden:
                pass # Can't DM user
            except Exception as e:
                logging.error(f"Failed to send warp feedback DM to {discord_id}: {e}")

        except Exception as e:
            logging.error(f"Failed to teleport {char_name}: {e}")


async def setup(bot):
    await bot.add_cog(WarpsCog(bot))