from discord.ext import commands, tasks
# Precisamos importar 'app_commands'
from discord import app_commands 
import discord
import logging
import secrets
import re
from datetime import datetime, timedelta
import os

import config

from bot import pending_registrations
from utils.database import DEFAULT_PLAYER_TRACKER_DB
from utils.database import link_discord_to_character

class RegistrationCog(commands.Cog, name="Registration"):
    """Handles player registration and account linking."""

    def __init__(self, bot):
        self.bot = bot
        self.process_registration_log_task.start()

    def cog_unload(self):
        self.process_registration_log_task.cancel()

    # --- INÍCIO DAS MUDANÇAS ---
    
    # 1. Trocamos @commands.command por @app_commands.command
    # 2. Adicionamos uma descrição
    @app_commands.command(name='registrar', description="Gera um código para vincular sua conta do jogo.")
    # 3. Adicionamos o cooldown no formato de app_command
    @app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
    # 4. Mudamos a assinatura de (self, ctx: commands.Context) para (self, interaction: discord.Interaction)
    async def register_command(self, interaction: discord.Interaction):
        # 5. Mudamos 'ctx.defer' para 'interaction.response.defer'
        await interaction.response.defer(ephemeral=True)
        
        registration_code = secrets.token_hex(4)
        pending_registrations[registration_code] = {
            # 6. Mudamos 'ctx.author.id' para 'interaction.user.id'
            'discord_id': interaction.user.id,
            'expires_at': datetime.utcnow() + timedelta(minutes=10)
        }
        try:
            message = (
                self.bot._("Olá! Para vincular sua conta do jogo à sua conta do Discord, entre no servidor e digite o seguinte comando no chat:\n\n")
                + f"```!registrar {registration_code}```\n"
                + self.bot._("Este código expira em 10 minutos.")
            )
            # 7. Mudamos 'ctx.author.send' para 'interaction.user.send'
            await interaction.user.send(message)
            # 8. Mudamos 'ctx.send' para 'interaction.followup.send' (pois usamos 'defer')
            await interaction.followup.send(self.bot._("Enviei a você uma mensagem privada com as instruções para o registro!"), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(self.bot._("Não consigo lhe enviar uma mensagem privada. Por favor, habilite as DMs de membros do servidor nas suas configurações de privacidade e tente novamente."), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(self.bot._("Ocorreu um erro ao tentar lhe enviar as instruções. Por favor, contate um administrador."), ephemeral=True)
            # 9. Mudamos 'ctx.author' para 'interaction.user'
            logging.error(f"Failed to send registration DM to {interaction.user}: {e}")

    # 10. Adicionamos um tratador de erro para o cooldown do app_command
    @register_command.error
    async def on_register_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"Comando em tempo de recarga. Tente novamente em {error.retry_after:.1f} segundos.", ephemeral=True)
        else:
            logging.error(f"Error in /registrar command: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Ocorreu um erro inesperado. Por favor, contate um administrador.", ephemeral=True)
            else:
                await interaction.followup.send("Ocorreu um erro inesperado. Por favor, contate um administrador.", ephemeral=True)

    # --- FIM DAS MUDANÇAS ---

    @tasks.loop(seconds=5)
    async def process_registration_log_task(self):
        now = datetime.utcnow()
        # Limpa códigos expirados
        expired_codes = [code for code, data in pending_registrations.items() if now > data.get('expires_at', now)]
        for code in expired_codes:
            if code in pending_registrations:
                del pending_registrations[code]

        # Processa registros pendentes
        for server_conf in config.SERVERS:
            log_path = server_conf.get("LOG_PATH")
            game_db_path = server_conf.get("DB_PATH") # Necessário para buscar o platform_id
            player_db_path = server_conf.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
            server_name = server_conf["NAME"]

            if not log_path or not os.path.exists(log_path):
                continue

            # Se o game.db não estiver configurado para este servidor, não podemos registrar
            if not game_db_path:
                continue

            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[-20:] # Lê as últimas 20 linhas
                    for line in lines:
                        if "!registrar" not in line:
                            continue

                        code_match = re.search(r"!registrar (\w+)", line)
                        if not code_match:
                            continue
                        
                        code = code_match.group(1).strip()

                        # Verifica se é um código válido e que ainda não foi processado
                        if code in pending_registrations and 'char_name' not in pending_registrations[code]:
                            char_match = re.search(r"ChatWindow: Character (.+?) \(uid", line)
                            if char_match:
                                char_name = char_match.group(1).strip()
                                reg_data = pending_registrations[code]
                                discord_id = reg_data['discord_id']

                                # Marca como processado para não tentar de novo na próxima varredura
                                pending_registrations[code]['char_name'] = char_name
                                logging.info(f"Registration code {code} used by character {char_name}. Attempting to link...")

                                # --- ESTA É A NOVA LÓGICA ---
                                # Tenta vincular a conta imediatamente buscando no game.db
                                success = link_discord_to_character(
                                    player_tracker_db_path=player_db_path,
                                    game_db_path=game_db_path,
                                    server_name=server_name,
                                    discord_id=discord_id,
                                    char_name=char_name
                                )

                                if success:
                                    logging.info(f"Successfully linked Discord user {discord_id} to character {char_name}.")
                                    try:
                                        user = await self.bot.fetch_user(discord_id)
                                        if user:
                                            # Envia a DM de sucesso que antes estava no rewards.py
                                            await user.send(self.bot._("Sucesso! Sua conta do jogo '{char}' foi vinculada à sua conta do Discord.").format(char=char_name))
                                    except Exception as e:
                                        logging.error(f"Failed to send success DM to {discord_id}: {e}")
                                    
                                    # Remove o registro pendente
                                    if code in pending_registrations:
                                        del pending_registrations[code]
                                else:
                                    logging.warning(f"Failed to link account for {char_name} ({discord_id}). Character not found in game.db?")
                                    # Você pode optar por enviar uma DM de falha aqui
                                    # E remover o código para não tentar novamente
                                    if code in pending_registrations:
                                        del pending_registrations[code]

            except Exception as e:
                logging.error(f"Error processing registration log for server {server_conf['NAME']}: {e}")

    @process_registration_log_task.before_loop
    async def before_process_registration_log_task(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RegistrationCog(bot))
