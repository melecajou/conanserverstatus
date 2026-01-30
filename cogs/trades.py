from discord.ext import commands, tasks
import discord
import logging
import re
import asyncio
import os
from datetime import datetime

import config
from utils.database import (
    get_char_id_by_name,
    get_item_in_backpack,
    find_discord_user_by_char_name
)
from utils.log_watcher import LogWatcher

# Constants
TRADE_SCAN_INTERVAL = 5
# Format: !buy item_key
BUY_COMMAND_REGEX = re.compile(r"!buy\s+(\w+)")
CHAT_CHARACTER_REGEX = re.compile(r"ChatWindow: Character (.+?) \(uid")

class TradesCog(commands.Cog, name="Trades"):
    """Handles in-game trade/shop commands."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.watchers = {}
        self.process_trade_log_task.start()

    def cog_unload(self):
        self.process_trade_log_task.cancel()

    @tasks.loop(seconds=TRADE_SCAN_INTERVAL)
    async def process_trade_log_task(self):
        """Scans logs for trade commands."""
        for server_conf in config.SERVERS:
            await self._process_log_for_server(server_conf)

    @process_trade_log_task.before_loop
    async def before_process_trade_task(self):
        await self.bot.wait_until_ready()

    async def _process_log_for_server(self, server_conf):
        log_path = server_conf.get("LOG_PATH")
        server_name = server_conf["NAME"]
        if not log_path:
            return

        if server_name not in self.watchers:
            self.watchers[server_name] = LogWatcher(log_path)

        new_lines = self.watchers[server_name].read_new_lines()
        for line in new_lines:
            await self._process_log_line(line, server_conf)

    async def _process_log_line(self, line, server_conf):
        if "!buy" not in line:
            return

        buy_match = BUY_COMMAND_REGEX.search(line)
        char_match = CHAT_CHARACTER_REGEX.search(line)

        if buy_match and char_match:
            item_key = buy_match.group(1).lower()
            char_name = char_match.group(1).strip()
            asyncio.create_task(self._handle_buy(char_name, item_key, server_conf))

    async def _handle_buy(self, char_name, item_key, server_conf):
        db_path = server_conf["DB_PATH"]
        server_name = server_conf["NAME"]
        user = None
        
        # 1. Check Config
        trade_config = getattr(config, "TRADE_ITEMS", {})
        if item_key not in trade_config:
            return

        item = trade_config[item_key]

        # 2. Find Discord User
        try:
            discord_id = find_discord_user_by_char_name(db_path, char_name)
            if not discord_id:
                logging.info(f"Unregistered player {char_name} tried to buy {item_key}")
                return
            
            user = await self.bot.fetch_user(int(discord_id))
        except Exception as e:
            logging.warning(f"Could not find or contact user for {char_name}: {e}")
            return

        if not user: return

        # 3. Initial DM Warning
        try:
            price_display = item.get('price_label', f"ID: {item['price_id']}")
            await user.send(
                self.bot._("🛒 **Purchase Request:** {label}\n💰 **Price:** {amount}x ({price_display})\n⏳ **Please wait 10 seconds** for synchronization. **DO NOT MOVE ITEMS IN BACKPACK!**").format(
                    label=item['label'], 
                    amount=item['price_amount'], 
                    price_display=price_display
                )
            )
        except Exception as e:
            logging.warning(f"Failed to send DM to {user.name}: {e}")
            return

        # 4. Wait for game.db sync
        await asyncio.sleep(8)

        # 5. Check Backpack
        try:
            char_id = get_char_id_by_name(db_path, char_name)
            if not char_id:
                await user.send(self.bot._("❌ Error: Character not found in database."))
                return

            backpack_item = get_item_in_backpack(db_path, char_id, item['price_id'])
            
            if not backpack_item or backpack_item['quantity'] < item['price_amount']:
                await user.send(self.bot._("❌ Insufficient funds! You need {amount}x {currency} in your backpack.").format(
                    amount=item['price_amount'], 
                    currency=price_display
                ))
                return

            # 6. RCON Transaction
            status_cog = self.bot.get_cog("Status")
            if not status_cog: return

            resp_list, _ = await status_cog.execute_rcon(server_name, "ListPlayers")
            idx = None
            for line in resp_list.split('\n'):
                if char_name in line:
                    idx = line.split('|')[0].strip()
                    break
            
            if idx is None:
                await user.send(self.bot._("❌ You must be online to complete the purchase."))
                return

            # A. Deduct
            new_qty = backpack_item['quantity'] - item['price_amount']
            await status_cog.execute_rcon(server_name, f"con {idx} SetInventoryItemIntStat {backpack_item['slot']} 1 {new_qty} 0")
            
            # B. Spawn
            await status_cog.execute_rcon(server_name, f"con {idx} SpawnItem {item['item_id']} {item['quantity']}")
            
            await user.send(self.bot._("✅ **Purchase complete!** Your item **{label}** was delivered to your backpack.").format(
                label=item['label']
            ))
            logging.info(f"TRADE SUCCESS: {char_name} bought {item_key}")

        except Exception as e:
            logging.error(f"Critical error in trade for {char_name}: {e}")
            try: await user.send(self.bot._("❌ A technical error occurred during processing. Please contact an Admin."))
            except: pass

async def setup(bot):
    await bot.add_cog(TradesCog(bot))