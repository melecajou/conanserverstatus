from discord.ext import commands
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

    @commands.command(name='setvip')
    @commands.has_permissions(administrator=True)
    async def set_vip_command(self, ctx: commands.Context, member: discord.Member, vip_level: int):
        """Define o nível de VIP para um membro do Discord. Uso: /setvip @usuario <nível>"""
        await ctx.defer(ephemeral=True)

        if vip_level < 0:
            await ctx.send(self.bot._("O nível de VIP não pode ser negativo."), ephemeral=True)
            return

        updated_in_server = None
        for server_conf in config.SERVERS:
            db_path = server_conf.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
            try:
                with sqlite3.connect(db_path) as con:
                    cur = con.cursor()
                    cur.execute("SELECT platform_id FROM player_time WHERE discord_id = ?", (str(member.id),))
                    result = cur.fetchone()

                    if result:
                        expiry_date_str = None
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
            await ctx.send(self.bot._("Nível de VIP para '{member}' atualizado para {level}.").format(member=member.display_name, level=vip_level), ephemeral=True)
        else:
            await ctx.send(self.bot._("Não foi encontrada uma conta de jogo vinculada para o membro '{member}'. O usuário precisa primeiro usar o comando /registrar.").format(member=member.display_name), ephemeral=True)
async def setup(bot):
    await bot.add_cog(AdminCog(bot))
