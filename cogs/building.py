from discord.ext import commands, tasks
import discord
import logging
import sqlite3
import os
import shutil

import config

def get_platform_id_for_player(player_id, game_db_path):
    """Gets the platform ID for a given player ID from the game DB."""
    if not player_id or not os.path.exists(game_db_path):
        return None
    try:
        with sqlite3.connect(f'file:{game_db_path}?mode=ro', uri=True) as con:
            cur = con.cursor()
            cur.execute("SELECT platformId FROM account WHERE id = ?", (player_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        logging.error(f"Failed to get platform ID for player {player_id}: {e}")
        return None

def get_vip_level_for_player(platform_id, player_db_path):
    """Gets the VIP level for a given platform ID from the player tracker DB."""
    if not platform_id or not os.path.exists(player_db_path):
        return 0
    try:
        with sqlite3.connect(f'file:{player_db_path}?mode=ro', uri=True) as con:
            cur = con.cursor()
            cur.execute("SELECT vip_level FROM player_time WHERE platform_id = ?", (platform_id,))
            result = cur.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logging.error(f"Failed to get VIP level for platform {platform_id}: {e}")
        return 0

def get_owner_details(owner_id, game_db_path, player_db_path):
    """Gets owner details (name, vip_level, type) from the game and player DBs."""
    if not os.path.exists(game_db_path):
        return None, 0, 'unknown'

    try:
        with sqlite3.connect(f'file:{game_db_path}?mode=ro', uri=True) as con:
            cur = con.cursor()

            # Check if it's a guild
            cur.execute("SELECT name FROM guilds WHERE guildId = ?", (owner_id,))
            guild_result = cur.fetchone()
            if guild_result:
                guild_name = guild_result[0]
                cur.execute("SELECT playerId FROM characters WHERE guild = ?", (owner_id,))
                members = cur.fetchall()
                max_vip = 0
                if members:
                    for member_pid in members:
                        platform_id = get_platform_id_for_player(member_pid[0], game_db_path)
                        if platform_id:
                            vip_level = get_vip_level_for_player(platform_id, player_db_path)
                            if vip_level > max_vip:
                                max_vip = vip_level
                return guild_name, max_vip, 'guild'

            # Check if it's a player
            cur.execute("SELECT char_name, playerId FROM characters WHERE id = ?", (owner_id,))
            char_result = cur.fetchone()
            if char_result:
                char_name, player_id = char_result
                platform_id = get_platform_id_for_player(player_id, game_db_path)
                if platform_id:
                    vip_level = get_vip_level_for_player(platform_id, player_db_path)
                    return char_name, vip_level, 'player'

    except Exception as e:
        logging.error(f"Failed to get owner details for owner_id {owner_id}: {e}")

    return None, 0, 'unknown'

class BuildingCog(commands.Cog, name="Building"):
    """Handles the hourly building reports."""

    def __init__(self, bot):
        self.bot = bot
        self.building_report_messages = {}
        self.update_building_report_task.start()

    def cog_unload(self):
        self.update_building_report_task.cancel()

    @tasks.loop(hours=1)
    async def update_building_report_task(self):
        for server_conf in config.SERVERS:
            watcher_config = server_conf.get("BUILDING_WATCHER")
            if not watcher_config or not watcher_config.get("ENABLED"):
                continue

            channel_id = watcher_config.get("CHANNEL_ID")
            sql_path = watcher_config.get("SQL_PATH")
            db_backup_path = watcher_config.get("DB_BACKUP_PATH")
            default_build_limit = watcher_config.get("BUILD_LIMIT", 99999)
            game_db_path = server_conf.get("DB_PATH")
            player_db_path = server_conf.get("PLAYER_DB_PATH")


            if not all([channel_id, sql_path, db_backup_path, game_db_path, player_db_path]):
                logging.error(self.bot._("Building Watcher for '{server_name}' is missing required configuration.").format(server_name=server_conf["NAME"]))
                continue

            logging.info(f"Starting building watcher for server: {server_conf['NAME']}")
            results = []
            try:
                with open(sql_path, 'r') as f:
                    sql_script = f.read()
                with sqlite3.connect(f'file:{db_backup_path}?mode=ro', uri=True) as con:
                    cur = con.cursor()
                    cur.execute(sql_script)
                    results = cur.fetchall()
                logging.info(f"Building watcher query successful for {server_conf['NAME']}. Found {len(results)} owners.")
            except Exception as e:
                logging.error(self.bot._("Failed to generate building report for '{server_name}'. Exception: {error}").format(server_name=server_conf["NAME"], error=e), exc_info=True)
                continue

            embed = discord.Embed(title=self.bot._("Building Report - {server_name}").format(server_name=server_conf['NAME']), color=discord.Color.blue())

            if not results:
                embed.description = self.bot._("No buildings found at the moment.")
            else:
                description_lines = []
                for i, (owner_id, pieces) in enumerate(results, 1):
                    owner_name, vip_level, owner_type = get_owner_details(owner_id, game_db_path, player_db_path)
                    
                    if not owner_name:
                        owner_name = self.bot._("(Unknown Owner)")

                    build_limit = default_build_limit
                    if vip_level == 1:
                        build_limit = 3500
                    elif vip_level == 2:
                        build_limit = 4000

                    line = f"**{i}.** {owner_name}: `{pieces}` peças (Premium: {vip_level}, Limite: {build_limit})"
                    
                    if pieces > build_limit:
                        line += self.bot._(" ⚠️ (Acima do limite)").format(build_limit=build_limit)
                    description_lines.append(line)
                
                full_description = "\n".join(description_lines)
                if len(full_description) > 4096:
                    full_description = full_description[:4090] + "\n..."
                embed.description = full_description

            embed.set_footer(text=self.bot._("Updated"))
            embed.timestamp = discord.utils.utcnow()

            try:
                logging.info(f"Attempting to post building report for {server_conf['NAME']} to channel {channel_id}.")
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logging.error(self.bot._("Building report channel {channel_id} not found.").format(channel_id=channel_id))
                    continue

                report_message = self.building_report_messages.get(channel_id)
                if report_message:
                    logging.info(f"Found cached message {report_message.id} for channel {channel_id}. Editing.")
                    await report_message.edit(embed=embed)
                    logging.info(f"Successfully edited message for {server_conf['NAME']}.")
                else:
                    logging.info(f"No cached message found for channel {channel_id}. Searching channel history.")
                    async for msg in channel.history(limit=50):
                        if msg.author.id == self.bot.user.id and msg.embeds and msg.embeds[0].title.startswith(self.bot._("Building Report")):
                            logging.info(f"Found message {msg.id} in history for channel {channel_id}. Caching and editing.")
                            self.building_report_messages[channel_id] = msg
                            await msg.edit(embed=embed)
                            logging.info(f"Successfully edited message for {server_conf['NAME']}.")
                            break
                    else:
                        logging.info(f"No message found in history for channel {channel_id}. Sending new message.")
                        new_msg = await channel.send(embed=embed)
                        self.building_report_messages[channel_id] = new_msg
                        logging.info(f"Successfully sent new message for {server_conf['NAME']}.")
            except Exception as e:
                logging.error(self.bot._("Failed to post building report for '{server_name}': {error}").format(server_name=server_conf["NAME"], error=e))

    @update_building_report_task.before_loop
    async def before_building_report_task(self):
        await self.bot.wait_until_ready()
        # Call the task once immediately
        await self.update_building_report_task.coro(self)

async def setup(bot):
    await bot.add_cog(BuildingCog(bot))
