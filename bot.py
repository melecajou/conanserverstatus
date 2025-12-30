import asyncio
import logging
import gettext

import discord
from discord.ext import commands

import config
from utils.database import (
    initialize_player_tracker_db,
    initialize_global_db,
    migrate_to_global_db,
    DEFAULT_PLAYER_TRACKER_DB,
)

# --- INTERNATIONALIZATION (i18n) SETUP ---
lang = getattr(config, "LANGUAGE", "en")
try:
    translation = gettext.translation("messages", localedir="locale", languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    _ = gettext.gettext

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s] [%(levelname)s] - %(message)s"
)

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
pending_registrations = {}
bot._ = _

# --- COG LIST ---
# Add new cogs here
COGS_TO_LOAD = [
    "cogs.status",
    "cogs.rewards",
    "cogs.admin",
    "cogs.registration",
    "cogs.building",
    "cogs.announcements",
    "cogs.warps",
    "cogs.guild_sync",
    "cogs.inactivity",
]


async def setup_hook():
    """A coroutine to be called to setup the bot."""
    # Initialize global registry
    initialize_global_db()
    
    # Collect all server DB paths for migration
    server_dbs = []
    for server_config in config.SERVERS:
        db_path = server_config.get("PLAYER_DB_PATH", DEFAULT_PLAYER_TRACKER_DB)
        server_dbs.append(db_path)
        initialize_player_tracker_db(db_path)

    # Perform migration to global registry
    migrate_to_global_db(server_dbs)

    # Load cogs
    for cog in COGS_TO_LOAD:
        try:
            await bot.load_extension(cog)
            logging.info(f"Loaded cog: {cog}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog}: {e}", exc_info=True)

    # Sync commands
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logging.error(e)


bot.setup_hook = setup_hook


# --- INITIALIZATION ---
if __name__ == "__main__":
    try:
        bot.run(config.STATUS_BOT_TOKEN)
    except Exception as e:
        logging.critical(_("Fatal error starting the bot: {error}").format(error=e))
