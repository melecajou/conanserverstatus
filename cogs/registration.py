from discord.ext import commands, tasks
import discord
import logging
import secrets
import re
from datetime import datetime, timedelta
import os

import config

pending_registrations = {}

class RegistrationCog(commands.Cog, name="Registration"):
    """Handles player registration and account linking."""

    def __init__(self, bot):
        self.bot = bot
        self.process_registration_log_task.start()

    def cog_unload(self):
        self.process_registration_log_task.cancel()

    @commands.command(name='registrar')
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def register_command(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        registration_code = secrets.token_hex(4)
        pending_registrations[registration_code] = {
            'discord_id': ctx.author.id,
            'expires_at': datetime.utcnow() + timedelta(minutes=10)
        }
        try:
            message = (
                self.bot._("Olá! Para vincular sua conta do jogo à sua conta do Discord, entre no servidor e digite o seguinte comando no chat:\n\n")
                + f"```!registrar {registration_code}```\n"
                + self.bot._("Este código expira em 10 minutos.")
            )
            await ctx.author.send(message)
            await ctx.send(self.bot._("Enviei a você uma mensagem privada com as instruções para o registro!"), ephemeral=True)
        except discord.Forbidden:
            await ctx.send(self.bot._("Não consigo lhe enviar uma mensagem privada. Por favor, habilite as DMs de membros do servidor nas suas configurações de privacidade e tente novamente."), ephemeral=True)
        except Exception as e:
            await ctx.send(self.bot._("Ocorreu um erro ao tentar lhe enviar as instruções. Por favor, contate um administrador."), ephemeral=True)
            logging.error(f"Failed to send registration DM to {ctx.author}: {e}")

    @tasks.loop(seconds=5)
    async def process_registration_log_task(self):
        now = datetime.utcnow()
        expired_codes = [code for code, data in pending_registrations.items() if now > data.get('expires_at', now)]
        for code in expired_codes:
            if code in pending_registrations:
                del pending_registrations[code]

        for server_conf in config.SERVERS:
            log_path = server_conf.get("LOG_PATH")
            if not log_path or not os.path.exists(log_path):
                continue

            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[-20:]
                    for line in lines:
                        if "!registrar" in line:
                            code_match = re.search(r"!registrar (\w+)", line)
                            if not code_match:
                                continue
                            code = code_match.group(1).strip()

                            if code in pending_registrations and 'char_name' not in pending_registrations[code]:
                                char_match = re.search(r"ChatWindow: Character (.+?) \(uid", line)
                                if char_match:
                                    char_name = char_match.group(1).strip()
                                    pending_registrations[code]['char_name'] = char_name
                                    logging.info(f"REG_DEBUG: Code {code} used by {char_name}. Pending final link.")
            except Exception as e:
                logging.error(f"Error processing registration log for server {server_conf['NAME']}: {e}")

    @process_registration_log_task.before_loop
    async def before_process_registration_log_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RegistrationCog(bot))
