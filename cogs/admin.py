from discord.ext import commands
from discord import app_commands
import discord
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import config
from utils.database import DEFAULT_PLAYER_TRACKER_DB


class AdminCog(commands.Cog, name="Admin"):
    """Admin commands for managing players."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setvip",
        description="Sets the VIP level for a member.",
    )
    @app_commands.describe(
        member="The Discord member to set the VIP level for.",
        level="The VIP level (0 = None, 1 = VIP, 2 = Super VIP, etc.)",
    )
    @app_commands.default_permissions(administrator=True)
    async def setvip(
        self, interaction: discord.Interaction, member: discord.Member, level: int
    ):
        """Sets the VIP level for a Discord member globally."""
        if level < 0:
            await interaction.response.send_message(
                self.bot._("The VIP level cannot be negative."), ephemeral=True
            )
            return

        from utils.database import set_global_vip
        success = set_global_vip(member.id, level)

        if success:
            await interaction.response.send_message(
                self.bot._("VIP level for '{member}' updated to {level}.").format(
                    member=member.display_name, level=level
                )
            )
        else:
            await interaction.response.send_message(
                self.bot._(
                    "An error occurred while updating the VIP level. Please check the logs."
                ),
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
