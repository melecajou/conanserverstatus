import asyncio
import logging
import gettext

import discord
from discord.ext import commands

import config
from database import initialize_player_tracker_db, DEFAULT_PLAYER_TRACKER_DB

# --- INTERNATIONALIZATION (i18n) SETUP ---
lang = getattr(config, 'LANGUAGE', 'en')
try:
    translation = gettext.translation('messages', localedir='locale', languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    _ = gettext.gettext

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bot._ = _

# --- COG LIST ---
# Add new cogs here
COGS_TO_LOAD = [
    'cogs.status',
    'cogs.rewards',
    'cogs.admin',
    'cogs.registration',
    'cogs.building',
    'cogs.announcements',
]

@bot.event
async def on_ready():
    logging.info(_('Bot connected as {username}').format(username=bot.user))

    # Initialize databases
    db_paths = {server.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB) for server in config.SERVERS}
    for db_path in db_paths:
        initialize_player_tracker_db(db_path)

    # Load cogs
    for cog in COGS_TO_LOAD:
        try:
            await bot.load_extension(cog)
        except Exception as e:
            logging.error(f"Failed to load cog {cog}: {e}")

    logging.info(_("All cogs loaded and tasks started."))


# --- INITIALIZATION ---
if __name__ == "__main__":
    try:
        bot.run(config.STATUS_BOT_TOKEN)
    except Exception as e:
        logging.critical(_("Fatal error starting the bot: {error}").format(error=e))
