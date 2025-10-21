from discord.ext import commands, tasks
import discord
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import config

class AnnouncementsCog(commands.Cog, name="Announcements"):
    """Handles scheduled announcements."""

    def __init__(self, bot):
        self.bot = bot
        self.announcements_sent_today = {}
        self.announcement_task.start()

    def cog_unload(self):
        self.announcement_task.cancel()

    @tasks.loop(minutes=1)
    async def announcement_task(self):
        for server_conf in config.SERVERS:
            ann_config = server_conf.get("ANNOUNCEMENTS")
            if not ann_config or not ann_config.get("ENABLED"):
                continue

            try:
                tz_str = ann_config.get("TIMEZONE", "UTC")
                now = datetime.now(ZoneInfo(tz_str))
                today = now.date()
                current_day_name = now.strftime('%A')
                
                channel_id = ann_config.get("CHANNEL_ID")
                if not channel_id:
                    continue

                for schedule_item in ann_config.get("SCHEDULE", []):
                    if schedule_item.get("DAY") == current_day_name and schedule_item.get("HOUR") == now.hour:
                        announcement_key = (server_conf["NAME"], schedule_item["DAY"])
                        if self.announcements_sent_today.get(announcement_key) != today:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                message = schedule_item.get("MESSAGE", self.bot._("Scheduled announcement."))
                                await channel.send(message)
                                logging.info(self.bot._("Sent announcement for '{server_name}' to channel {channel_id}.").format(server_name=server_conf['NAME'], channel_id=channel_id))
                                self.announcements_sent_today[announcement_key] = today
                            else:
                                logging.error(self.bot._("Could not find announcement channel with ID {channel_id} for server '{server_name}'.").format(channel_id=channel_id, server_name=server_conf['NAME']))
            except Exception as e:
                logging.error(self.bot._("Error in announcement task for server '{server_name}': {error}").format(server_name=server_conf['NAME'], error=e))

    @announcement_task.before_loop
    async def before_announcement_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(AnnouncementsCog(bot))
