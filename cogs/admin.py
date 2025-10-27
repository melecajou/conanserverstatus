from discord.ext import commands
from discord import app_commands
import discord
import logging
import sqlite3
from datetime import datetime, timedelta

import config
from utils.database import DEFAULT_PLAYER_TRACKER_DB

class AdminCog(commands.Cog, name="Admin"):
    """Admin commands for managing players."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='setvip', description="Define o nível de VIP para um membro do Discord.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_vip_command(self, interaction: discord.Interaction, member: discord.Member, vip_level: int):
        await interaction.response.defer(ephemeral=True)

        if vip_level < 0:
            await interaction.followup.send(self.bot._("O nível de VIP não pode ser negativo."), ephemeral=True)
            return

        updated_in_server = None
        for server_conf in config.SERVERS:
            db_path = server_conf.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
            try:
                with sqlite3.connect(db_path) as con:
                    cur = con.cursor()
                    cur.execute("SELECT platform_id FROM player_time WHERE discord_id = ?", (str(member.id),))
                    result = cur.fetchone()

                    expiry_date_str = None
                    if result:
                        if vip_level > 0:
                            expiry_date = datetime.utcnow() + timedelta(days=30)
                            expiry_date_str = expiry_date.strftime("%Y-%m-%d")

                        cur.execute("UPDATE player_time SET vip_level = ?, vip_expiry_date = ? WHERE discord_id = ?", 
                                    (vip_level, expiry_date_str, str(member.id)))
                        con.commit()
                        updated_in_server = server_conf["NAME"]
            except Exception as e:
                logging.error(f"Error in setvip command for server {server_conf['NAME']}: {e}")

        if updated_in_server:
            await interaction.followup.send(self.bot._("Nível de VIP para '{member}' atualizado para {level}.").format(member=member.display_name, level=vip_level), ephemeral=True)
        else:
            await interaction.followup.send(self.bot._("Não foi encontrada uma conta de jogo vinculada para o membro '{member}'. O usuário precisa primeiro usar o comando /registrar.").format(member=member.display_name), ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
