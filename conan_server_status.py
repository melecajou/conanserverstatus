# conan_server_status.py

"""
Discord bot to monitor the status of MULTIPLE Conan Exiles servers.
It maintains a status message for each server in its respective channel,
updating them periodically and asynchronously.
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

# --- INTERNATIONALIZATION (i18n) SETUP ---
# Determines the language to use from the config, with a fallback to 'en'
lang = getattr(config, 'LANGUAGE', 'en')

# Set up gettext to find the translation files
try:
    translation = gettext.translation('messages', localedir='locale', languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    # Fallback to a dummy function if the translation file is not found
    _ = gettext.gettext

# Configure logger
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Dictionary to track status messages
status_messages: Dict[int, discord.Message] = {}


# --- CORE FUNCTIONS ---

async def get_server_status_embed(server_config: dict) -> discord.Embed:
    """
    Generates a Discord Embed with the status of a specific server.
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
                description=_("The server is operating normally."),
                color=discord.Color.green()
            )
            
            if player_names:
                formatted_list = "\n".join(f"• {name}" for name in player_names)
                embed.add_field(name=_("Online Players ({count})").format(count=len(player_names)), value=formatted_list, inline=False)
            else:
                embed.add_field(name=_("Online Players (0)"), value=_("No one is playing at the moment."), inline=False)
            
            embed.set_footer(text=_("Status updated"))
            embed.timestamp = discord.utils.utcnow()
            return embed

        except Exception as e:
            logging.warning(f"[{server_name}] " + _("RCON connection attempt {attempt}/{max_retries} failed: {error}").format(attempt=attempt + 1, max_retries=max_retries, error=e))
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay_seconds)
        finally:
            await client.close() 
    
    # If all attempts fail
    logging.error(f"[{server_name}] " + _("All RCON connection attempts have failed."))
    embed = discord.Embed(
        title=f"❌ {server_name}",
        description=_("Could not connect to the server. It may be offline or restarting."),
        color=discord.Color.red()
    )
    embed.set_footer(text=_("Check the console or contact an administrator."))
    embed.timestamp = discord.utils.utcnow()
    return embed


# --- DISCORD TASKS AND EVENTS ---

@tasks.loop(minutes=1)
async def update_all_statuses_task():
    for server_conf in config.SERVERS:
        channel_id = server_conf["STATUS_CHANNEL_ID"]
        channel = bot.get_channel(channel_id)
        if not channel:
            logging.error(_("Channel with ID {channel_id} for '{server_name}' not found.").format(channel_id=channel_id, server_name=server_conf['NAME']))
            continue

        new_embed = await get_server_status_embed(server_conf)
        status_message = status_messages.get(channel_id)
        
        try:
            if status_message:
                await status_message.edit(embed=new_embed)
            else:
                new_msg = await channel.send(embed=new_embed)
                status_messages[channel_id] = new_msg
                logging.info(_("New status message created for '{server_name}' in channel {channel_name}.").format(server_name=server_conf['NAME'], channel_name=channel.name))
        except discord.errors.NotFound:
            logging.warning(_("Message for '{server_name}' not found. Creating a new one.").format(server_name=server_conf['NAME']))
            new_msg = await channel.send(embed=new_embed)
            status_messages[channel_id] = new_msg
        except Exception as e:
            logging.error(_("Error updating status for '{server_name}': {error}").format(server_name=server_conf['NAME'], error=e))
            if channel_id in status_messages:
                del status_messages[channel_id]

@bot.event
async def on_ready():
    logging.info(_('Bot connected as {username}').format(username=bot.user))
    for server_conf in config.SERVERS:
        channel_id = server_conf["STATUS_CHANNEL_ID"]
        channel = bot.get_channel(channel_id)
        if channel:
            async for msg in channel.history(limit=50):
                if msg.author.id == bot.user.id:
                    status_messages[channel_id] = msg
                    logging.info(_("Found message for '{server_name}' in channel {channel_name}.").format(server_name=server_conf['NAME'], channel_name=channel.name))
                    break
    if not update_all_statuses_task.is_running():
        update_all_statuses_task.start()
        logging.info(_("Status update task started."))


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
        await ctx.send(_("Command on cooldown. Try again in {seconds:.1f} seconds.").format(seconds=error.retry_after), delete_after=5, ephemeral=True)


# --- INITIALIZATION ---

if __name__ == "__main__":
    try:
        bot.run(config.STATUS_BOT_TOKEN)
    except Exception as e:
        logging.critical(_("Fatal error starting the bot: {error}").format(error=e))