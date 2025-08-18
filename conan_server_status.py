# conan_server_status.py

"""
Bot do Discord para monitorar o status de MÚLTIPLOS servidores Conan Exiles.
Ele mantém uma mensagem de status para cada servidor em seu respectivo canal,
atualizando-as periodicamente de forma assíncrona.
"""

import asyncio
import gettext
import logging
import os
from typing import Dict

import discord
from discord.ext import commands, tasks
from aiomcrcon import Client

import config

# --- CONFIGURAÇÃO DE INTERNACIONALIZAÇÃO (i18n) ---
# Determina o idioma a ser usado a partir da configuração, com fallback para 'en'
lang = getattr(config, 'LANGUAGE', 'en')

# Configura o gettext para encontrar os arquivos de tradução
try:
    translation = gettext.translation('messages', localedir='locale', languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    # Fallback para uma função dummy se o arquivo de tradução não for encontrado
    _ = gettext.gettext

# Configura o logger
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

# --- CONFIGURAÇÃO DO BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Dicionário para rastrear as mensagens
status_messages: Dict[int, discord.Message] = {}


# --- FUNÇÕES CORE ---

async def get_server_status_embed(server_config: dict) -> discord.Embed:
    """
    Gera um Embed do Discord com o status de um servidor específico.
    """
    max_retries = 3
    retry_delay_seconds = 5
    server_name = server_config["NAME"]

    for attempt in range(max_retries):
        client = Client(
            server_config["SERVER_IP"], 
            server_config["RCON_PORT"], 
            server_config["RCON_PASS"]
        )
        try:
            await client.connect()
            response = (await client.send_cmd("ListPlayers"))[0]
            
            player_lines = response.split('\n')[1:]
            player_names = [line.split()[2] for line in player_lines if line.strip()]

            embed = discord.Embed(
                title=f"✅ {server_name}",
                description=_("O servidor está operando normalmente."),
                color=discord.Color.green()
            )
            
            if player_names:
                formatted_list = "\n".join(f"• {name}" for name in player_names)
                embed.add_field(name=_("Jogadores Online ({count})").format(count=len(player_names)), value=formatted_list, inline=False)
            else:
                embed.add_field(name=_("Jogadores Online (0)"), value=_("Ninguém está jogando no momento."), inline=False)
            
            embed.set_footer(text=_("Status atualizado"))
            embed.timestamp = discord.utils.utcnow()
            return embed

        except Exception as e:
            logging.warning(f"[{server_name}] " + _("Tentativa {attempt}/{max_retries} de conexão RCON falhou: {error}").format(attempt=attempt + 1, max_retries=max_retries, error=e))
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay_seconds)
        finally:
            await client.close()
    
    # Se todas as tentativas falharem
    logging.error(f"[{server_name}] " + _("Todas as tentativas de conexão RCON falharam."))
    embed = discord.Embed(
        title=f"❌ {server_name}",
        description=_("Não foi possível conectar ao servidor. Pode estar desligado ou reiniciando."),
        color=discord.Color.red()
    )
    embed.set_footer(text=_("Verifique o console ou contate um administrador."))
    embed.timestamp = discord.utils.utcnow()
    return embed


# --- TAREFAS E EVENTOS DO DISCORD

@tasks.loop(minutes=1)
async def update_all_statuses_task():
    for server_conf in config.SERVERS:
        channel_id = server_conf["STATUS_CHANNEL_ID"]
        channel = bot.get_channel(channel_id)
        if not channel:
            logging.error(_("Canal com ID {channel_id} para '{server_name}' não encontrado.").format(channel_id=channel_id, server_name=server_conf['NAME']))
            continue

        new_embed = await get_server_status_embed(server_conf)
        status_message = status_messages.get(channel_id)
        
        try:
            if status_message:
                await status_message.edit(embed=new_embed)
            else:
                new_msg = await channel.send(embed=new_embed)
                status_messages[channel_id] = new_msg
                logging.info(_("Nova mensagem de status criada para '{server_name}' no canal {channel_name}.").format(server_name=server_conf['NAME'], channel_name=channel.name))
        except discord.errors.NotFound:
            logging.warning(_("Mensagem para '{server_name}' não encontrada. Criando uma nova.").format(server_name=server_conf['NAME']))
            new_msg = await channel.send(embed=new_embed)
            status_messages[channel_id] = new_msg
        except Exception as e:
            logging.error(_("Erro ao atualizar status para '{server_name}': {error}").format(server_name=server_conf['NAME'], error=e))
            if channel_id in status_messages:
                del status_messages[channel_id]

@bot.event
async def on_ready():
    logging.info(_('Bot conectado como {username}').format(username=bot.user))
    for server_conf in config.SERVERS:
        channel_id = server_conf["STATUS_CHANNEL_ID"]
        channel = bot.get_channel(channel_id)
        if channel:
            async for msg in channel.history(limit=50):
                if msg.author.id == bot.user.id:
                    status_messages[channel_id] = msg
                    logging.info(_("Mensagem encontrada para '{server_name}' no canal {channel_name}.").format(server_name=server_conf['NAME'], channel_name=channel.name))
                    break
    if not update_all_statuses_task.is_running():
        update_all_statuses_task.start()
        logging.info(_("Tarefa de atualização de status iniciada."))


@bot.command(name='status')
@commands.cooldown(1, 30, commands.BucketType.user)
async def server_status_command(ctx: commands.Context):
    await ctx.defer()
    tasks = [get_server_status_embed(server_conf) for server_conf in config.SERVERS]
    embeds = await asyncio.gather(*tasks)
    await ctx.send(embeds=embeds)

@server_status_command.error
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(_("Comando em tempo de recarga. Tente novamente em {seconds:.1f} segundos.").format(seconds=error.retry_after), delete_after=5, ephemeral=True)


# --- INICIALIZAÇÃO ---

if __name__ == "__main__":
    try:
        bot.run(config.STATUS_BOT_TOKEN)
    except Exception as e:
        logging.critical(_("Erro fatal ao iniciar o bot: {error}").format(error=e))
