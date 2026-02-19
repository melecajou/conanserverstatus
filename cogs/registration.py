from discord.ext import commands, tasks
from discord import app_commands
import discord
import logging
import asyncio
import secrets
import re
from datetime import datetime, timedelta, timezone
import os

import config
from bot import pending_registrations
from utils.database import link_discord_to_character, link_discord_to_platform
from utils.log_watcher import LogWatcher

# Constants
REGISTRATION_EXPIRY_MINUTES = 10
LOG_SCAN_INTERVAL_SECONDS = 5
LOG_LINES_TO_READ = 20
REGISTRATION_COMMAND_REGEX = re.compile(r"!register ([\w-]+)")
CHAT_CHARACTER_REGEX = re.compile(r"ChatWindow: Character (.+?) \(uid")


class RegistrationCog(commands.Cog, name="Registration"):
    """Handles player registration and account linking."""

    def __init__(self, bot):
        self.bot = bot
        # Watcher storage: {server_name: LogWatcher}
        self.log_watchers = {}
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

        registration_code = secrets.token_urlsafe(6)
        pending_registrations[registration_code] = {
            "discord_id": interaction.user.id,
            "guild_id": interaction.guild_id,
            "expires_at": datetime.now(timezone.utc)
            + timedelta(minutes=REGISTRATION_EXPIRY_MINUTES),
        }

        try:
            message = (
                self.bot._(
                    "Hello! To link your game account to your Discord account, please enter the following command in the in-game chat:\n\n"
                )
                + f"```!register {registration_code}```\n"
                + self.bot._("This code will expire in {minutes} minutes.").format(
                    minutes=REGISTRATION_EXPIRY_MINUTES
                )
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

    @app_commands.command(
        name="finduser",
        description="Finds a Discord user by their in-game character name.",
    )
    @app_commands.describe(char_name="The character name to search for.")
    async def finduser(self, interaction: discord.Interaction, char_name: str):
        """Finds a discord user by character name."""
        await interaction.response.defer(ephemeral=True)

        from utils.database import find_discord_user_by_char_name

        found_discord_id = None

        # Search across all servers
        for server_conf in config.SERVERS:
            db_path = server_conf.get("DB_PATH")
            if not db_path:
                continue

            discord_id = find_discord_user_by_char_name(db_path, char_name)
            if discord_id:
                found_discord_id = discord_id
                break

        if found_discord_id:
            try:
                user = await self.bot.fetch_user(found_discord_id)
                await interaction.followup.send(
                    f"✅ O personagem **{char_name}** pertence ao usuário: {user.mention} (`{user.name}`)",
                    ephemeral=True,
                )
            except discord.NotFound:
                await interaction.followup.send(
                    f"⚠️ Encontrei o ID Discord `{found_discord_id}` para **{char_name}**, mas o usuário não está acessível (pode ter saído do servidor).",
                    ephemeral=True,
                )
        else:
            await interaction.followup.send(
                f"❌ Não encontrei nenhum usuário vinculado ao personagem **{char_name}**.",
                ephemeral=True,
            )

    @app_commands.command(
        name="sync_roles",
        description="Syncs the registered role to all linked users (Admin only).",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_roles_command(self, interaction: discord.Interaction):
        """
        Iterates through all player databases, finds linked Discord users,
        and assigns the registered role to them in the current guild.
        """
        if not hasattr(config, "REGISTERED_ROLE_ID") or not config.REGISTERED_ROLE_ID:
            await interaction.response.send_message(
                "REGISTERED_ROLE_ID is not configured.", ephemeral=True
            )
            return

        role = interaction.guild.get_role(config.REGISTERED_ROLE_ID)
        if not role:
            await interaction.response.send_message(
                f"Role with ID {config.REGISTERED_ROLE_ID} not found in this guild.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        count = 0
        import sqlite3

        # Collect all unique Discord IDs from all configured servers
        linked_discord_ids = set()

        for server in config.SERVERS:
            player_db = server.get("PLAYER_DB_PATH")
            if not player_db or not os.path.exists(player_db):
                continue

            try:
                with sqlite3.connect(player_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT DISTINCT discord_id FROM player_time WHERE discord_id IS NOT NULL"
                    )
                    rows = cursor.fetchall()
                    for row in rows:
                        if row[0]:
                            try:
                                linked_discord_ids.add(int(row[0]))
                            except ValueError:
                                pass
            except Exception as e:
                logging.error(f"Error reading DB {player_db}: {e}")

        # Assign roles
        for discord_id in linked_discord_ids:
            try:
                member = await interaction.guild.fetch_member(discord_id)
                if member and role not in member.roles:
                    await member.add_roles(role)
                    count += 1
            except discord.NotFound:
                continue  # User not in server
            except Exception as e:
                logging.error(f"Error syncing role for {discord_id}: {e}")

        await interaction.followup.send(
            f"Role sync complete. Added role to {count} users.", ephemeral=True
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
            if server_name not in self.log_watchers:
                self.log_watchers[server_name] = LogWatcher(log_path)

            watcher = self.log_watchers[server_name]
            lines = await watcher.read_new_lines()

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
        if (
            code in pending_registrations
            and "char_name" not in pending_registrations[code]
        ):
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if char_match:
                char_name = char_match.group(1).strip()
                reg_data = pending_registrations[code]
                discord_id = reg_data["discord_id"]
                guild_id = reg_data.get("guild_id")

                # Mark as processed to prevent duplicate handling
                pending_registrations[code]["char_name"] = char_name

                await self._link_account_and_notify(
                    code,
                    discord_id,
                    char_name,
                    player_db_path,
                    game_db_path,
                    server_name,
                    guild_id,
                )

    @staticmethod
    def _get_platform_id_sync(player_db_path: str, server_name: str, discord_id: int):
        import sqlite3

        try:
            with sqlite3.connect(player_db_path) as con:
                cur = con.cursor()
                cur.execute(
                    "SELECT platform_id FROM player_time WHERE server_name = ? AND discord_id = ?",
                    (server_name, str(discord_id)),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logging.error(f"Error retrieving platform_id after link: {e}")
        return None

    async def _link_account_and_notify(
        self,
        code: str,
        discord_id: int,
        char_name: str,
        player_db_path: str,
        game_db_path: str,
        server_name: str,
        guild_id: int = None,
    ):
        """Links the game account to the Discord ID and notifies the user."""
        logging.info(
            f"Registration code {code} used by character {char_name}. Attempting to link..."
        )

        # Link in server-specific DB (ensures platform_id is known locally)
        success_local = await asyncio.to_thread(
            link_discord_to_character,
            player_tracker_db_path=player_db_path,
            game_db_path=game_db_path,
            server_name=server_name,
            discord_id=discord_id,
            char_name=char_name,
        )

        if success_local:
            # Get the platform_id that was just identified
            platform_id = await asyncio.to_thread(
                self._get_platform_id_sync, player_db_path, server_name, discord_id
            )

            # Link globally
            if platform_id:
                await asyncio.to_thread(link_discord_to_platform, platform_id, discord_id)

            logging.info(
                f"Successfully linked Discord user {discord_id} to character {char_name} on server {server_name}."
            )

            # Apply Role
            if (
                guild_id
                and hasattr(config, "REGISTERED_ROLE_ID")
                and config.REGISTERED_ROLE_ID
            ):
                try:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        member = await guild.fetch_member(discord_id)
                        role = guild.get_role(config.REGISTERED_ROLE_ID)
                        if member and role:
                            await member.add_roles(role)
                            logging.info(
                                f"Assigned role {role.name} to {member.display_name}"
                            )
                except Exception as e:
                    logging.error(f"Failed to assign role to {discord_id}: {e}")

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
