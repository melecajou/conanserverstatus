from discord.ext import commands
from discord import app_commands
import discord
import logging
import sqlite3
import asyncio
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
        days="Optional: Duration in days for the reward benefits. Leave empty for permanent.",
    )
    @app_commands.default_permissions(administrator=True)
    async def setvip(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        level: int,
        days: int = None,
    ):
        """Sets the VIP level for a Discord member globally."""
        if level < 0:
            await interaction.response.send_message(
                self.bot._("The VIP level cannot be negative."), ephemeral=True
            )
            return

        expiry_date = None
        if days and days > 0:
            expiry_dt = datetime.now() + timedelta(days=days)
            expiry_date = expiry_dt.isoformat()

        from utils.database import set_global_vip

        success = await asyncio.to_thread(set_global_vip, member.id, level, expiry_date)

        if success:
            msg = self.bot._("VIP level for '{member}' updated to {level}.").format(
                member=member.display_name, level=level
            )
            if expiry_date:
                msg += f" (Expira em {days} dias para recompensas)"
            else:
                msg += " (Vitalício)"

            await interaction.response.send_message(msg)
        else:
            await interaction.response.send_message(
                self.bot._(
                    "An error occurred while updating the VIP level. Please check the logs."
                ),
                ephemeral=True,
            )

    @app_commands.command(
        name="premium",
        description="Checks your current VIP status and expiration.",
    )
    async def premium(self, interaction: discord.Interaction):
        """Checks the user's own VIP status."""
        from utils.database import get_global_vip

        data = await asyncio.to_thread(get_global_vip, interaction.user.id)

        if not data or data["vip_level"] == 0:
            await interaction.response.send_message(
                "✨ Você não possui um nível VIP ativo no momento.", ephemeral=True
            )
            return

        level = data["vip_level"]
        expiry = data["vip_expiry"]

        msg = f"💎 **Seu Status Premium:**\n"
        msg += f"• **Nível:** {level}\n"

        if expiry:
            expiry_dt = datetime.fromisoformat(expiry)
            msg += f"• **Vantagem de Recompensas expira em:** {expiry_dt.strftime('%d/%m/%Y %H:%M')}\n"
            msg += "• **Vantagem de Construção:** Permanente ✅"
        else:
            msg += "• **Duração:** Vitalício ✅"

        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(
        name="checkvip",
        description="Checks the VIP status of a specific member (Admin only).",
    )
    @app_commands.describe(member="The member to check.")
    @app_commands.default_permissions(administrator=True)
    async def checkvip(self, interaction: discord.Interaction, member: discord.Member):
        """Checks the VIP status of another member."""
        from utils.database import get_global_vip

        data = await asyncio.to_thread(get_global_vip, member.id)

        if not data or data["vip_level"] == 0:
            await interaction.response.send_message(
                f"ℹ️ O usuário **{member.display_name}** não possui nível VIP.",
                ephemeral=True,
            )
            return

        level = data["vip_level"]
        expiry = data["vip_expiry"]

        msg = f"🔍 **Status VIP de {member.display_name}:**\n"
        msg += f"• **Nível:** {level}\n"

        if expiry:
            expiry_dt = datetime.fromisoformat(expiry)
            msg += f"• **Expiração (Recompensas):** {expiry_dt.strftime('%d/%m/%Y %H:%M')}\n"
        else:
            msg += "• **Duração:** Vitalício ✅"

        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(
        name="listvips",
        description="Lists all players with an active VIP level (Admin only).",
    )
    @app_commands.default_permissions(administrator=True)
    async def listvips(self, interaction: discord.Interaction):
        """Lists all current VIPs."""
        from utils.database import get_all_vips

        vips = await asyncio.to_thread(get_all_vips)

        if not vips:
            await interaction.response.send_message(
                "❌ Nenhum jogador VIP encontrado.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="💎 Lista de Jogadores VIP",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )

        for v in vips:
            try:
                # Try to get member object to show display name
                member = interaction.guild.get_member(v["discord_id"])
                name = member.display_name if member else f"ID: {v['discord_id']}"
            except:
                name = f"ID: {v['discord_id']}"

            expiry = v["vip_expiry"]
            if expiry:
                expiry_dt = datetime.fromisoformat(expiry)
                status = f"Expira em: {expiry_dt.strftime('%d/%m/%Y')}"
            else:
                status = "Vitalício ✅"

            embed.add_field(
                name=name,
                value=f"**Nível:** {v['vip_level']}\n**Status:** {status}",
                inline=True,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="setvipexpiry",
        description="Updates the expiration days for an existing VIP (Admin only).",
    )
    @app_commands.describe(
        member="The member to update.", days="New duration in days from now."
    )
    @app_commands.default_permissions(administrator=True)
    async def setvipexpiry(
        self, interaction: discord.Interaction, member: discord.Member, days: int
    ):
        """Updates the expiry of a VIP member."""
        if days < 0:
            await interaction.response.send_message(
                "O número de dias não pode ser negativo.", ephemeral=True
            )
            return

        from utils.database import update_vip_expiry

        success = await asyncio.to_thread(update_vip_expiry, member.id, days)

        if success:
            await interaction.response.send_message(
                f"✅ Prazo de recompensas para **{member.display_name}** atualizado para **{days} dias** a partir de agora.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"❌ Erro: O usuário **{member.display_name}** não foi encontrado na base VIP ou ocorreu um erro.",
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
