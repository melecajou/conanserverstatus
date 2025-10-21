from discord.ext import commands, tasks
import discord
import logging
import sqlite3
import os
import shutil

import config

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
            build_limit = watcher_config.get("BUILD_LIMIT", 99999)

            if not all([channel_id, sql_path, db_backup_path]):
                logging.error(self.bot._("Building Watcher for '{server_name}' is missing required configuration.").format(server_name=server_conf["NAME"]))
                continue

            results = []
            try:
                with open(sql_path, 'r') as f:
                    sql_script = f.read()
                with sqlite3.connect(f'file:{db_backup_path}?mode=ro', uri=True) as con:
                    cur = con.cursor()
                    cur.execute(sql_script)
                    results = cur.fetchall()
            except Exception as e:
                logging.error(self.bot._("Failed to generate building report for '{server_name}'. Exception: {error}").format(server_name=server_conf["NAME"], error=e), exc_info=True)

            embed = discord.Embed(title=self.bot._("Building Report - {server_name}").format(server_name=server_conf['NAME']), color=discord.Color.blue())

            if not results:
                embed.description = self.bot._("No buildings found at the moment.")
            else:
                description_lines = []
                for i, (owner, pieces) in enumerate(results, 1):
                    owner_name = owner if owner else self.bot._("(No Owner)")
                    line = f"**{i}.** {owner_name}: `{pieces}` peças"
                    if pieces > build_limit:
                        line += self.bot._(" ⚠️ (Above the limit of {build_limit})").format(build_limit=build_limit)
                    description_lines.append(line)
                full_description = "\n".join(description_lines)
                if len(full_description) > 4096:
                    full_description = full_description[:4090] + "\n..."
                embed.description = full_description

            embed.set_footer(text=self.bot._("Updated"))
            embed.timestamp = discord.utils.utcnow()

            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logging.error(self.bot._("Building report channel {channel_id} not found.").format(channel_id=channel_id))
                    continue

                report_message = self.building_report_messages.get(channel_id)
                if report_message:
                    await report_message.edit(embed=embed)
                else:
                    async for msg in channel.history(limit=50):
                        if msg.author.id == self.bot.user.id and msg.embeds and msg.embeds[0].title.startswith(self.bot._("Building Report")):
                            self.building_report_messages[channel_id] = msg
                            await msg.edit(embed=embed)
                            break
                    else:
                        new_msg = await channel.send(embed=embed)
                        self.building_report_messages[channel_id] = new_msg
            except Exception as e:
                logging.error(self.bot._("Failed to post building report for '{server_name}': {error}").format(server_name=server_conf["NAME"], error=e))

    @update_building_report_task.before_loop
    async def before_building_report_task(self):
        await self.bot.wait_until_ready()
        # Call the task once immediately
        await self.update_building_report_task.coro(self)

async def setup(bot):
    await bot.add_cog(BuildingCog(bot))
