from discord.ext import commands, tasks
import discord
import logging
import asyncio
import config
from utils.database import get_all_guild_members

class GuildSyncCog(commands.Cog, name="GuildSync"):
    """Synchronizes in-game guilds with Discord roles."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.sync_guilds_task.start()

    def cog_unload(self):
        self.sync_guilds_task.cancel()

    @tasks.loop(minutes=30)
    async def sync_guilds_task(self):
        """Main loop to sync guild roles."""
        sync_config = getattr(config, "GUILD_SYNC", {})
        if not sync_config.get("ENABLED"):
            return

        guild_id = sync_config.get("SERVER_ID") # Discord Server ID
        if not guild_id:
            return

        discord_guild = self.bot.get_guild(guild_id)
        if not discord_guild:
            return

        prefix = sync_config.get("ROLE_PREFIX", "🛡️ ")
        
        # 1. Get Game Data: {discord_id: ["Guild Name 1", "Guild Name 2"]}
        server_dbs = [s.get("DB_PATH") for s in config.SERVERS if s.get("DB_PATH")]
        user_guild_map = get_all_guild_members(server_dbs)

        logging.info(f"Starting Guild Sync for {len(user_guild_map)} users...")

        # 2. Iterate through Discord Members
        # We fetch all members to ensure we catch everyone (requires Intents.members)
        async for member in discord_guild.fetch_members(limit=None):
            if member.bot:
                continue

            current_game_guilds = user_guild_map.get(member.id, [])
            expected_role_names = {f"{prefix}{name}" for name in current_game_guilds}
            
            # Identify roles to remove (Start with prefix AND not in expected list)
            roles_to_remove = []
            for role in member.roles:
                if role.name.startswith(prefix) and role.name not in expected_role_names:
                    roles_to_remove.append(role)

            # Identify roles to add
            roles_to_add = []
            for role_name in expected_role_names:
                role = discord.utils.get(discord_guild.roles, name=role_name)
                
                # Create role if it doesn't exist
                if not role:
                    try:
                        role = await discord_guild.create_role(
                            name=role_name, 
                            mentionable=True, 
                            hoist=True, 
                            reason="Conan Guild Sync"
                        )
                        logging.info(f"Created new guild role (hoisted): {role_name}")
                        await asyncio.sleep(1) # API Rate limit safety
                    except Exception as e:
                        logging.error(f"Failed to create role {role_name}: {e}")
                        continue
                
                if role not in member.roles:
                    roles_to_add.append(role)

            # Apply Changes
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Left Guild (Game Sync)")
                    logging.info(f"Removed guild roles from {member.display_name}: {[r.name for r in roles_to_remove]}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logging.error(f"Error removing roles from {member.display_name}: {e}")

            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason="Joined Guild (Game Sync)")
                    logging.info(f"Added guild roles to {member.display_name}: {[r.name for r in roles_to_add]}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logging.error(f"Error adding roles to {member.display_name}: {e}")

        # 3. Cleanup Empty Guild Roles
        # If a role starts with the prefix and has 0 members, delete it.
        # Check config to see if cleanup is enabled
        if sync_config.get("CLEANUP_EMPTY_ROLES", True):
            for role in discord_guild.roles:
                if role.name.startswith(prefix) and len(role.members) == 0:
                    try:
                        await role.delete(reason="Empty Guild Role Cleanup")
                        logging.info(f"Deleted empty guild role: {role.name}")
                        await asyncio.sleep(1)
                    except Exception as e:
                        logging.error(f"Failed to delete role {role.name}: {e}")

        logging.info("Guild Sync completed.")

    @sync_guilds_task.before_loop
    async def before_sync_task(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(GuildSyncCog(bot))
