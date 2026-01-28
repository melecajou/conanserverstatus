from discord.ext import commands, tasks
import discord
import logging
import os
from datetime import datetime

import config
from utils.database import get_inactive_structures

class InactivityCog(commands.Cog, name="Inactivity"):
    """Periodically generates reports on inactive players and their structures."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.inactivity_report_task.start()

    def cog_unload(self):
        self.inactivity_report_task.cancel()

    @tasks.loop(hours=24)
    async def inactivity_report_task(self):
        """Generates the inactivity report for each configured server."""
        for server_conf in config.SERVERS:
            report_config = server_conf.get("INACTIVITY_REPORT")
            if not report_config or not report_config.get("ENABLED"):
                continue

            channel_id = report_config.get("CHANNEL_ID")
            days = report_config.get("DAYS", 15)
            sql_path = report_config.get("SQL_PATH", "sql/inactive_structures.sql")
            game_db_path = server_conf.get("DB_PATH")
            server_name = server_conf["NAME"]

            if not all([channel_id, game_db_path]):
                logging.error(f"Inactivity Report for '{server_name}' missing configuration.")
                continue

            channel = self.bot.get_channel(channel_id)
            if not channel:
                logging.error(f"Inactivity Report channel {channel_id} not found.")
                continue

            logging.info(f"Generating inactivity report for {server_name}...")
            
            # Fetch data using the provided SQL
            inactive_data = get_inactive_structures(game_db_path, sql_path, days)

            if not inactive_data:
                # Optional: Send a message saying everything is clean
                # await channel.send(f"✅ **{server_name}**: Nenhuma base inativa (>{days} dias) encontrada.")
                continue

            # Format and Send Report
            embed = discord.Embed(
                title=self.bot._("🕵️‍♂️ Inactivity Report - {server}").format(server=server_name),
                description=self.bot._("Listing of bases whose owner/clan has been offline for more than **{days} days**.").format(days=days),
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            report_lines = []
            for item in inactive_data:
                line = f"• **{item['owner']}**: `{item['pieces']}` " + self.bot._("pieces") + f"\n  └ Last: {item['last_activity']}\n  └ `{item['location']}`"
                report_lines.append(line)

            # Discord Embed Limit is 4096 chars. If larger, send multiple messages.
            chunks = []
            current_chunk = ""
            for line in report_lines:
                if len(current_chunk) + len(line) + 2 > 4000:
                    chunks.append(current_chunk)
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            if current_chunk:
                chunks.append(current_chunk)

            for i, chunk in enumerate(chunks):
                embed.description = self.bot._("Inactive bases (>{days} days) - Part {part}/{total}\n\n").format(
                    days=days, 
                    part=i+1, 
                    total=len(chunks)
                ) + chunk
                await channel.send(embed=embed)

            logging.info(f"Inactivity report sent for {server_name} ({len(inactive_data)} entries).")

    @inactivity_report_task.before_loop
    async def before_inactivity_report_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(InactivityCog(bot))