
# conan_server_status.py

"""
Discord bot to monitor the status of MULTIPLE Conan Exiles servers.
It maintains a status message for each server in its respective channel,
updating them periodically and asynchronously.
It also tracks player online time and rewards them at a configurable interval.
"""

import asyncio
import gettext
import logging
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

import discord
from discord.ext import commands, tasks
from aiomcrcon import Client

import config

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

# --- DATABASE SETUP ---
PLAYER_TRACKER_DB = "data/playertracker.db"

def initialize_player_tracker_db():
    """Creates the player tracker database (data/playertracker.db) and table if they don't exist."""
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(PLAYER_TRACKER_DB), exist_ok=True)
        con = sqlite3.connect(PLAYER_TRACKER_DB)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_time (
                platform_id TEXT NOT NULL,
                server_name TEXT NOT NULL,
                online_minutes INTEGER DEFAULT 0,
                last_rewarded_hour INTEGER DEFAULT 0,
                PRIMARY KEY (platform_id, server_name)
            )
        """)
        con.commit()
        con.close()
        logging.info(_("Player tracker database '{db}' initialized successfully.").format(db=PLAYER_TRACKER_DB))
    except Exception as e:
        logging.critical(_("Failed to initialize player tracker database: {error}").format(error=e))

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
status_messages: Dict[int, discord.Message] = {}


# --- CORE FUNCTIONS ---

def get_player_level(db_path: str, char_name: str) -> int:
    """Queries the game database to get the level of a character."""
    if not db_path:
        return 0
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cur = con.cursor()
        cur.execute("SELECT level FROM characters WHERE char_name = ?", (char_name,))
        result = cur.fetchone()
        con.close()
        if result:
            return result[0]
    except Exception as e:
        logging.error(_("Could not read player level from {db}: {error}").format(db=db_path, error=e))
    return 0

def log_reward_to_file(server_name: str, player_name: str, online_minutes: int, item_id: str, quantity: int):
    """Appends a record of a player reward to 'logs/rewards.log'."""
    log_file = "logs/rewards.log"
    try:
        # Ensure the logs directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Convert minutes to a more readable format, e.g., "Xh Ym"
        hours, minutes = divmod(online_minutes, 60)
        playtime_str = f"{hours}h {minutes}m"

        log_entry = (
            f"[{timestamp}] Server: {server_name}, Player: {player_name}, "
            f"Total Playtime: {playtime_str}, "
            f"Reward: {quantity}x item {item_id}\n"
        )
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logging.error(f"Failed to write to reward log file: {e}")


async def track_and_reward_players(server_conf: dict, player_lines: List[str], rcon_client: Client):
    """
    Tracks player online time and issues rewards based on settings in config.py.
    This system can be enabled/disabled and the reward interval is configurable.
    """
    reward_config = getattr(config, 'REWARD_CONFIG', {})
    if not reward_config.get('ENABLED', False):
        return

    # Get reward interval, default to 120 minutes if not specified or invalid
    try:
        reward_interval = int(reward_config.get('REWARD_INTERVAL_MINUTES', 120))
        if reward_interval <= 0:
            reward_interval = 120
    except (ValueError, TypeError):
        reward_interval = 120

    server_name = server_conf["NAME"]
    online_players = []
    for line in player_lines:
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) > 4:
            online_players.append({
                "idx": parts[0].strip(),
                "char_name": parts[1].strip(),
                "platform_id": parts[4].strip()
            })

    if not online_players:
        return

    try:
        con = sqlite3.connect(PLAYER_TRACKER_DB)
        cur = con.cursor()

        for player in online_players:
            platform_id = player["platform_id"]

            # Add player to DB if they don't exist
            cur.execute("INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)", (platform_id, server_name))

            # Increment online time
            cur.execute("UPDATE player_time SET online_minutes = online_minutes + 1 WHERE platform_id = ? AND server_name = ?", (platform_id, server_name))

            # Check for reward
            cur.execute("SELECT online_minutes, last_rewarded_hour FROM player_time WHERE platform_id = ? AND server_name = ?", (platform_id, server_name))
            result = cur.fetchone()
            if not result:
                continue

            online_minutes, last_rewarded_hour = result
            current_hour_milestone = online_minutes // reward_interval

            if current_hour_milestone > last_rewarded_hour:
                # Calculate the actual hours played for the log message
                total_hours_played = current_hour_milestone * (reward_interval / 60.0)
                logging.info(_("Player {player} on server '{server}' reached a new reward milestone at {hours:.1f} hours. Issuing reward.").format(player=player['char_name'], server=server_name, hours=total_hours_played))
                
                item_id = reward_config["REWARD_ITEM_ID"]
                quantity = reward_config["REWARD_QUANTITY"]
                command = f"con {player['idx']} SpawnItem {item_id} {quantity}"
                
                try:
                    response, _unused = await rcon_client.send_cmd(command)
                    logging.info(_("Reward command '{cmd}' for player {player} on server '{server}' executed. Response: {resp}").format(cmd=command, player=player['char_name'], server=server_name, resp=response.strip()))
                    
                    # Log the reward to the text file
                    log_reward_to_file(
                        server_name,
                        player['char_name'],
                        online_minutes,
                        item_id,
                        quantity
                    )

                    # Update rewarded hour in DB
                    cur.execute("UPDATE player_time SET last_rewarded_hour = ? WHERE platform_id = ? AND server_name = ?", (current_hour_milestone, platform_id, server_name))

                except Exception as e:
                    logging.error(_("Failed to send reward RCON command for player {player} on server '{server}': {error}").format(player=player['char_name'], server=server_name, error=e))
        
        con.commit()
        con.close()

    except Exception as e:
        logging.error(_("An error occurred during player time tracking and reward for server '{server}': {error}").format(server=server_name, error=e))


async def get_server_status_embed(server_config: dict, rcon_client: Client) -> Optional[discord.Embed]:
    """Generates a Discord Embed with the status of a specific server."""
    server_name = server_config["NAME"]
    db_path = server_config.get("DB_PATH")

    try:
        response, _unused = await rcon_client.send_cmd("ListPlayers")
        player_lines = response.split('\n')[1:]

        # --- Reward Tracking ---
        await track_and_reward_players(server_config, player_lines, rcon_client)
        # ---

        player_char_names = [line.split('|')[1].strip() for line in player_lines if line.strip()]

        embed = discord.Embed(
            title=f"✅ {server_name}",
            description=_("The server is operating normally."),
            color=discord.Color.green()
        )

        if player_char_names:
            player_details = []
            for name in player_char_names:
                level = get_player_level(db_path, name)
                if level > 0:
                    player_details.append(f"• {name} ({level})")
                else:
                    player_details.append(f"• {name}")
            embed.add_field(name=_("Online Players ({count})").format(count=len(player_char_names)), value="\n".join(player_details), inline=False)
        else:
            embed.add_field(name=_("Online Players (0)"), value=_("No one is playing at the moment."), inline=False)

        embed.set_footer(text=_("Status updated"))
        embed.timestamp = discord.utils.utcnow()
        return embed

    except Exception as e:
        logging.error(_("Failed to generate server status embed for '{server}': {error}").format(server=server_name, error=e))
        return None


# --- DISCORD TASKS AND EVENTS ---

async def attempt_rcon_connection(server_conf: dict) -> Optional[Client]:
    """Tries to connect to RCON, retrying a few times on failure."""
    rcon_client = Client(server_conf["SERVER_IP"], server_conf["RCON_PORT"], server_conf["RCON_PASS"])
    for attempt in range(3):
        try:
            await rcon_client.connect()
            logging.info(_("[{server}] RCON connection successful on attempt {attempt}/3.").format(server=server_conf['NAME'], attempt=attempt + 1))
            return rcon_client  # Return the connected client
        except Exception as e:
            logging.warning(
                _("[{server}] RCON connection attempt {attempt}/3 failed: {error}").format(
                    server=server_conf['NAME'], attempt=attempt + 1, error=e
                )
            )
            await rcon_client.close() # Ensure connection is closed before retrying
            if attempt < 2:  # If not the last attempt
                await asyncio.sleep(attempt + 2)  # Wait 2s, then 3s
    return None  # Return None if all attempts fail


@tasks.loop(minutes=1)
async def update_all_statuses_task():
    """Main task that runs every minute to update server statuses and track players."""
    for server_conf in config.SERVERS:
        channel_id = server_conf["STATUS_CHANNEL_ID"]
        channel = bot.get_channel(channel_id)
        if not channel:
            logging.error(_("Channel with ID {channel_id} for '{server_name}' not found.").format(channel_id=channel_id, server_name=server_conf['NAME']))
            continue

        new_embed = None
        rcon_client = await attempt_rcon_connection(server_conf)

        if rcon_client:
            try:
                new_embed = await get_server_status_embed(server_conf, rcon_client)
            except Exception as e:
                logging.error(_("Failed to get server status for '{server}' after connecting: {error}").format(server=server_conf['NAME'], error=e))
            finally:
                await rcon_client.close()

        # If rcon_client is None (connection failed) or new_embed is None (error in get_server_status_embed)
        if not new_embed:
            new_embed = discord.Embed(
                title=f"❌ {server_conf['NAME']}",
                description=_("Could not connect to the server. It may be offline or restarting."),
                color=discord.Color.red()
            )
            new_embed.set_footer(text=_("Check the console or contact an administrator."))
            new_embed.timestamp = discord.utils.utcnow()

        if not new_embed: # This should not be strictly necessary anymore, but as a safeguard.
            continue

        try:
            status_message = status_messages.get(channel_id)
            if status_message:
                await status_message.edit(embed=new_embed)
            else:
                new_msg = await channel.send(embed=new_embed)
                status_messages[channel_id] = new_msg
        except discord.errors.NotFound:
            logging.warning(_("Message for '{server}' not found. Creating a new one.").format(server=server_conf['NAME']))
            new_msg = await channel.send(embed=new_embed)
            status_messages[channel_id] = new_msg
        except Exception as e:
            logging.error(_("Error updating status message for '{server}': {error}").format(server=server_conf['NAME'], error=e))
            if channel_id in status_messages:
                del status_messages[channel_id]


@bot.event
async def on_ready():
    logging.info(_('Bot connected as {username}').format(username=bot.user))
    initialize_player_tracker_db()
    
    for server_conf in config.SERVERS:
        channel_id = server_conf["STATUS_CHANNEL_ID"]
        channel = bot.get_channel(channel_id)
        if channel:
            async for msg in channel.history(limit=50):
                if msg.author.id == bot.user.id:
                    status_messages[channel_id] = msg
                    break
    
    if not update_all_statuses_task.is_running():
        update_all_statuses_task.start()
        logging.info(_("Status update and reward task started."))


@bot.command(name='status')
@commands.cooldown(1, 30, commands.BucketType.user)
async def server_status_command(ctx: commands.Context):
    """Manual command to show server status."""
    await ctx.defer()
    await ctx.send(_("This command is being reworked. The bot updates automatically every minute."))


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
