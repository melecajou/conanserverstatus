from discord.ext import commands, tasks
from discord import app_commands
import discord
import logging
import secrets
import re
from datetime import datetime, timedelta, timezone
import os

import config
from bot import pending_registrations
from utils.database import link_discord_to_character

# Constants
REGISTRATION_EXPIRY_MINUTES = 10
LOG_SCAN_INTERVAL_SECONDS = 5
LOG_LINES_TO_READ = 20
REGISTRATION_COMMAND_REGEX = re.compile(r"!register (\w+)")
CHAT_CHARACTER_REGEX = re.compile(r"ChatWindow: Character (.+?) \(uid")

class RegistrationCog(commands.Cog, name="Registration"):
    """Handles player registration and account linking."""

    def __init__(self, bot):
        self.bot = bot
        self.process_registration_log_task.start()

    def cog_unload(self):
        """Clean up the cog before unloading."""
        self.process_registration_log_task.cancel()

    @app_commands.command(
        name="register",
        description="Generates a code to link your in-game account.",
    )
    @app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
    async def register_command(self, interaction: discord.Interaction):
        """
        Handles the /register command, generating a unique code for the user
        and sending them instructions via DM.
        """
        await interaction.response.defer(ephemeral=True)

        registration_code = secrets.token_hex(4)
        pending_registrations[registration_code] = {
            "discord_id": interaction.user.id,
            "expires_at": datetime.now(timezone.utc)
            + timedelta(minutes=REGISTRATION_EXPIRY_MINUTES),
        }

        try:
            message = (
                self.bot._(
                    "Hello! To link your game account to your Discord account, please enter the following command in the in-game chat:\n\n"
                )
                + f"```!register {registration_code}```\n"
                + self.bot._(
                    "This code will expire in {minutes} minutes."
                ).format(minutes=REGISTRATION_EXPIRY_MINUTES)
            )
            await interaction.user.send(message)
            await interaction.followup.send(
                self.bot._(
                    "I have sent you a private message with the registration instructions!"
                ),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                self.bot._(
                    "I cannot send you a private message. Please enable DMs from server members in your privacy settings and try again."
                ),
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                self.bot._(
                    "An error occurred while trying to send you the instructions. Please contact an administrator."
                ),
                ephemeral=True,
            )
            logging.error(f"Failed to send registration DM to {interaction.user}: {e}")

    @register_command.error
    async def on_register_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Handles errors for the /register command."""
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                self.bot._(
                    "This command is on cooldown. Please try again in {seconds:.1f} seconds."
                ).format(seconds=error.retry_after),
                ephemeral=True,
            )
        else:
            logging.error(f"Error in registration command: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    self.bot._(
                        "An unexpected error occurred. Please contact an administrator."
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    self.bot._(
                        "An unexpected error occurred. Please contact an administrator."
                    ),
                    ephemeral=True,
                )

    def _clear_expired_registrations(self):
        """Removes registration codes that have expired."""
        now = datetime.now(timezone.utc)
        expired_codes = [
            code
            for code, data in pending_registrations.items()
            if now > data.get("expires_at", now)
        ]
        for code in expired_codes:
            if code in pending_registrations:
                del pending_registrations[code]

    async def _process_log_for_server(self, server_conf: dict):
        """Processes the log file for a single server to find registration attempts."""
        log_path = server_conf.get("LOG_PATH")
        game_db_path = server_conf.get("DB_PATH")
        player_db_path = server_conf.get("PLAYER_DB_PATH")
        server_name = server_conf["NAME"]

        if not all([log_path, game_db_path, player_db_path]) or not os.path.exists(
            log_path
        ):
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-LOG_LINES_TO_READ:]
                for line in lines:
                    await self._process_log_line(
                        line, game_db_path, player_db_path, server_name
                    )
        except Exception as e:
            logging.error(
                f"Error processing registration log for server {server_name}: {e}"
            )

    async def _process_log_line(
        self, line: str, game_db_path: str, player_db_path: str, server_name: str
    ):
        """Parses a single log line for a registration code and processes it."""
        if "!register" not in line:
            return

        code_match = REGISTRATION_COMMAND_REGEX.search(line)
        if not code_match:
            return

        code = code_match.group(1).strip()
        if code in pending_registrations and "char_name" not in pending_registrations[
            code
        ]:
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if char_match:
                char_name = char_match.group(1).strip()
                reg_data = pending_registrations[code]
                discord_id = reg_data["discord_id"]

                # Mark as processed to prevent duplicate handling
                pending_registrations[code]["char_name"] = char_name

                await self._link_account_and_notify(
                    code, discord_id, char_name, player_db_path, game_db_path, server_name
                )

    async def _link_account_and_notify(
        self,
        code: str,
        discord_id: int,
        char_name: str,
        player_db_path: str,
        game_db_path: str,
        server_name: str,
    ):
        """Links the game account to the Discord ID and notifies the user."""
        logging.info(
            f"Registration code {code} used by character {char_name}. Attempting to link..."
        )
        success = link_discord_to_character(
            player_tracker_db_path=player_db_path,
            game_db_path=game_db_path,
            server_name=server_name,
            discord_id=discord_id,
            char_name=char_name,
        )

        if success:
            logging.info(
                f"Successfully linked Discord user {discord_id} to character {char_name} on server {server_name}."
            )
            try:
                user = await self.bot.fetch_user(discord_id)
                if user:
                    await user.send(
                        self.bot._(
                            "Success! Your game account '{char}' has been linked to your Discord account."
                        ).format(char=char_name)
                    )
            except Exception as e:
                logging.error(f"Failed to send success DM to {discord_id}: {e}")
        else:
            logging.warning(
                f"Failed to link account for {char_name} ({discord_id}). Character not found in game.db?"
            )
            # Optionally, send a failure DM here

        # Clean up the processed registration
        if code in pending_registrations:
            del pending_registrations[code]

    @tasks.loop(seconds=LOG_SCAN_INTERVAL_SECONDS)
    async def process_registration_log_task(self):
        """
        Periodically scans server logs for registration commands and processes them.
        """
        self._clear_expired_registrations()
        for server_conf in config.SERVERS:
            await self._process_log_for_server(server_conf)

    @process_registration_log_task.before_loop
    async def before_process_registration_log_task(self):
        """Waits for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(RegistrationCog(bot))
