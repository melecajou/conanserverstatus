import discord
from discord.ext import commands, tasks
import logging
import re
import asyncio
import struct
import sqlite3
import json

import config
from utils.database import (
    get_char_id_by_name,
    find_discord_user_by_char_name,
    get_player_balance,
    update_player_balance,
    log_market_action,
    GLOBAL_DB_PATH
)
from utils.log_watcher import LogWatcher

# Regex for in-game commands
# !deposit <slot>
DEPOSIT_COMMAND_REGEX = re.compile(r"!deposit\s+(\d+)")
# !sell <slot> <price>
SELL_COMMAND_REGEX = re.compile(r"!sell\s+(\d+)\s+(\d+)")
# !buy <listing_id>
BUY_COMMAND_REGEX = re.compile(r"!buy\s+(\d+)")
# !balance
BALANCE_COMMAND_REGEX = re.compile(r"!balance")
# !market
MARKET_COMMAND_REGEX = re.compile(r"!market")
# !withdraw <amount>
WITHDRAW_COMMAND_REGEX = re.compile(r"!withdraw\s+(\d+)")
CHAT_CHARACTER_REGEX = re.compile(r"ChatWindow: Character (.+?) \(uid")

class MarketplaceCog(commands.Cog, name="Marketplace"):
    """Asynchronous P2P Marketplace and Virtual Economy."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.watchers = {}
        # Blacklist IDs that should not be duplicated (Instance IDs)
        self.dna_blacklist = [22]
        self.process_logs_task.start()

    def cog_unload(self):
        self.process_logs_task.cancel()

    @tasks.loop(seconds=5)
    async def process_logs_task(self):
        """Monitor logs for marketplace commands."""
        if not getattr(config, "MARKETPLACE", {}).get("ENABLED", False):
            return

        for server_conf in config.SERVERS:
            await self._process_log_for_server(server_conf)

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
        # 1. Handle Deposit
        if "!deposit" in line:
            dep_match = DEPOSIT_COMMAND_REGEX.search(line)
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if dep_match and char_match:
                slot = int(dep_match.group(1))
                char_name = char_match.group(1).strip()
                asyncio.create_task(self._handle_deposit(char_name, slot, server_conf))
        
        # 2. Handle Sell
        elif "!sell" in line:
            sell_match = SELL_COMMAND_REGEX.search(line)
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if sell_match and char_match:
                slot = int(sell_match.group(1))
                price = int(sell_match.group(2))
                char_name = char_match.group(1).strip()
                asyncio.create_task(self._handle_sell(char_name, slot, price, server_conf))

        # 3. Handle Buy
        elif "!buy" in line:
            buy_match = BUY_COMMAND_REGEX.search(line)
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if buy_match and char_match:
                listing_id = int(buy_match.group(1))
                char_name = char_match.group(1).strip()
                asyncio.create_task(self._handle_buy(char_name, listing_id, server_conf))

        # 4. Handle Balance
        elif "!balance" in line:
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if char_match:
                char_name = char_match.group(1).strip()
                asyncio.create_task(self._handle_balance(char_name, server_conf))

        # 5. Handle Market List
        elif "!market" in line:
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if char_match:
                char_name = char_match.group(1).strip()
                asyncio.create_task(self._handle_market_list(char_name, server_conf))

        # 6. Handle Withdraw
        elif "!withdraw" in line:
            withdraw_match = WITHDRAW_COMMAND_REGEX.search(line)
            char_match = CHAT_CHARACTER_REGEX.search(line)
            if withdraw_match and char_match:
                amount = int(withdraw_match.group(1))
                char_name = char_match.group(1).strip()
                asyncio.create_task(self._handle_withdraw(char_name, amount, server_conf))

    async def _handle_withdraw(self, char_name, amount, server_conf):
        """Converts virtual balance back to physical currency item via RCON SpawnItem."""
        db_path = server_conf["DB_PATH"]
        server_name = server_conf["NAME"]
        currency_id = config.MARKETPLACE["CURRENCY_ITEM_ID"]

        if amount <= 0: return

        # 1. Identity Check
        discord_id = find_discord_user_by_char_name(db_path, char_name)
        if not discord_id: return
        user = await self.bot.fetch_user(int(discord_id))
        if not user: return

        # 2. Check Balance
        balance = get_player_balance(int(discord_id))
        if balance < amount:
            try: await user.send(self.bot._("❌ Insufficient funds for withdrawal. Balance: {balance}").format(balance=balance))
            except: pass
            return

        # 3. Execute Transaction
        try:
            status_cog = self.bot.get_cog("Status")
            if not status_cog: return

            resp_list, _ = await status_cog.execute_rcon(server_name, "ListPlayers")
            idx = None
            for line in resp_list.splitlines():
                if char_name in line:
                    m = re.search(r"^\s*(\d+)\s*\|", line)
                    if m: idx = m.group(1); break
            
            if idx is None:
                await user.send(self.bot._("❌ You must be online to withdraw."))
                return

            # A. Deduct from Virtual Wallet
            if update_player_balance(int(discord_id), -amount):
                # B. Spawn physical item
                print(f"MARKET: Withdrawal of {amount} for {char_name}")
                await status_cog.execute_rcon(server_name, f"con {idx} SpawnItem {currency_id} {amount}")
                
                log_market_action(int(discord_id), "WITHDRAW", f"Withdrew {amount} of virtual currency to physical item.")
                new_balance = get_player_balance(int(discord_id))
                await user.send(self.bot._("✅ **Withdrawal Successful!**\n📤 **Amount:** {qty}\n💰 **Remaining Balance:** {balance} {currency}").format(
                    qty=amount, balance=new_balance, currency=config.MARKETPLACE["CURRENCY_NAME"]
                ))
                logging.info(f"MARKET: {char_name} withdrew {amount} coins.")
            else:
                await user.send("❌ Internal error during withdrawal.")

        except Exception as e:
            logging.error(f"Critical error in withdraw for {char_name}: {e}")

    async def _handle_balance(self, char_name, server_conf):
        """Sends current virtual balance to player via DM."""
        db_path = server_conf["DB_PATH"]
        discord_id = find_discord_user_by_char_name(db_path, char_name)
        if not discord_id: return
        user = await self.bot.fetch_user(int(discord_id))
        if user:
            balance = get_player_balance(int(discord_id))
            await user.send(self.bot._("💰 **Your Wallet:** {balance} {currency}").format(
                balance=balance, currency=config.MARKETPLACE["CURRENCY_NAME"]
            ))

    async def _handle_market_list(self, char_name, server_conf):
        """Sends a list of active market listings to player via DM."""
        db_path = server_conf["DB_PATH"]
        discord_id = find_discord_user_by_char_name(db_path, char_name)
        if not discord_id: return
        user = await self.bot.fetch_user(int(discord_id))
        if not user: return

        try:
            with sqlite3.connect(GLOBAL_DB_PATH) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT id, item_template_id, price FROM market_listings WHERE status = 'active' ORDER BY created_at DESC LIMIT 10")
                rows = cur.fetchall()
            
            if not rows:
                await user.send(self.bot._("🏪 **Marketplace:** No active listings at the moment."))
                return

            msg = self.bot._("🏪 **Active Marketplace Listings (Last 10):**\n")
            for row in rows:
                msg += f"🔹 **#{row['id']}** | ID: {row['item_template_id']} | 💰 {row['price']} {config.MARKETPLACE['CURRENCY_NAME']}\n"
            
            msg += self.bot._("\nType `!buy <id>` in-game to purchase.")
            await user.send(msg)
        except Exception as e:
            logging.error(f"Error listing market: {e}")

    async def _handle_buy(self, char_name, listing_id, server_conf):
        """Processes a purchase: checks balance, transfers funds, and delivers DNA-perfect item."""
        db_path = server_conf["DB_PATH"]
        server_name = server_conf["NAME"]
        
        # 1. Identity Check
        discord_id = find_discord_user_by_char_name(db_path, char_name)
        if not discord_id: return
        
        user = await self.bot.fetch_user(int(discord_id))
        if not user: return

        # 2. Fetch Listing Data
        listing = None
        try:
            with sqlite3.connect(GLOBAL_DB_PATH) as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT * FROM market_listings WHERE id = ? AND status = 'active'", (listing_id,))
                listing = cur.fetchone()
        except Exception as e:
            logging.error(f"Error fetching listing {listing_id}: {e}")
            return

        if not listing:
            try: await user.send(self.bot._("❌ Error: Listing #{id} not found or already sold.").format(id=listing_id))
            except: pass
            return

        if int(listing['seller_discord_id']) == int(discord_id):
            try: await user.send(self.bot._("❌ Error: You cannot buy your own listing."))
            except: pass
            return

        price = listing['price']
        seller_discord_id = listing['seller_discord_id']
        template_id = listing['item_template_id']
        dna = json.loads(listing['item_dna'])

        # 3. Check for existing items to avoid stacking issues
        try:
            char_id = get_char_id_by_name(db_path, char_name)
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
                # Check Backpack (0) and Hotbar (2). Stacking doesn't happen with Equipped (1).
                exists = con.execute("SELECT 1 FROM item_inventory WHERE owner_id=? AND template_id=? AND inv_type IN (0, 2)", (char_id, template_id)).fetchone()
            
            if exists:
                try: await user.send(self.bot._("❌ **Stacking Alert:** You already have item ID {tid} in your inventory. Please store it in a chest before buying to ensure a clean delivery.").format(tid=template_id))
                except: pass
                return
        except Exception as e:
            logging.error(f"Error checking existing items for {char_name}: {e}")

        # 4. Check Balance
        buyer_balance = get_player_balance(int(discord_id))
        if buyer_balance < price:
            try: await user.send(self.bot._("❌ Insufficient funds! Price: {price} {currency}. Your balance: {balance}.").format(
                price=price, currency=config.MARKETPLACE["CURRENCY_NAME"], balance=buyer_balance
            ))
            except: pass
            return

        # 4. Start Transaction
        try:
            # A. Update Balances
            if not update_player_balance(int(discord_id), -price):
                raise Exception("Failed to deduct funds from buyer.")
            
            update_player_balance(seller_discord_id, price) # Add to seller (can be offline)

            # B. Mark Listing as Sold
            with sqlite3.connect(GLOBAL_DB_PATH) as con:
                con.execute("UPDATE market_listings SET status = 'sold' WHERE id = ?", (listing_id,))
                con.commit()

            # C. Spawn Item (RCON)
            status_cog = self.bot.get_cog("Status")
            if not status_cog: raise Exception("Status Cog not found.")

            resp_list, _ = await status_cog.execute_rcon(server_name, "ListPlayers")
            idx = None
            for line in resp_list.splitlines():
                if char_name in line:
                    m = re.search(r"^\s*(\d+)\s*\|", line)
                    if m: idx = m.group(1); break
            
            if idx is None:
                # Refund logic if player logged out exactly now (very rare but possible)
                update_player_balance(int(discord_id), price)
                update_player_balance(seller_discord_id, -price)
                with sqlite3.connect(GLOBAL_DB_PATH) as con:
                    con.execute("UPDATE market_listings SET status = 'active' WHERE id = ?", (listing_id,))
                    con.commit()
                await user.send(self.bot._("❌ You logged out! Purchase canceled and refunded."))
                return

            # Capture inventory state BEFORE spawn (with quantities)
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
                char_id = get_char_id_by_name(db_path, char_name)
                # We store a dict: {(item_id, inv_type): data_blob_or_quantity}
                # But to keep it simple and effective, let's just track the whole row
                before_items = { (row[0], row[1]): row[2] for row in con.execute("SELECT item_id, inv_type, template_id FROM item_inventory WHERE owner_id=?", (char_id,)).fetchall() }

            print(f"MARKET: Spawning item {template_id} for buyer {char_name}")
            await status_cog.execute_rcon(server_name, f"con {idx} SpawnItem {template_id} 1")
            
            # D. Find New Item and Inject DNA (with retries)
            new_item_found = None # (slot, inv_type)
            for attempt in range(4): # Try up to 4 times
                await asyncio.sleep(6 if attempt == 0 else 4)
                
                with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
                    after_rows = con.execute("SELECT item_id, inv_type, template_id FROM item_inventory WHERE owner_id=? AND template_id=?", (char_id, template_id)).fetchall()
                
                # Check for a completely new slot first
                for row in after_rows:
                    key = (row[0], row[1])
                    if key not in before_items:
                        new_item_found = key
                        break
                
                if new_item_found: break

                # If no new slot, check if an existing slot of the same template was updated 
                # (This happens with stackables)
                if not new_item_found:
                    for row in after_rows:
                        key = (row[0], row[1])
                        # If the slot existed before but now we are looking at it again...
                        # In Conan, sometimes the data blob changes when quantity increases.
                        # For simplicity, if we spawned it and it's stackable, we can assume the first matching template.
                        new_item_found = key
                        break
                
                if new_item_found: break
                print(f"MARKET: Attempt {attempt+1} to find spawned item {template_id} failed. Retrying...")

            if new_item_found:
                new_slot, inv_type = new_item_found
                print(f"MARKET: Injecting DNA into Slot {new_slot} ({inv_type})")
                for p_id, v in dna.get("int", {}).items():
                    await status_cog.execute_rcon(server_name, f"con {idx} SetInventoryItemIntStat {new_slot} {p_id} {v} {inv_type}")
                for p_id, v in dna.get("float", {}).items():
                    await status_cog.execute_rcon(server_name, f"con {idx} SetInventoryItemFloatStat {new_slot} {p_id} {v} {inv_type}")
                
                log_market_action(int(discord_id), "BUY", f"Bought listing #{listing_id} (Item {template_id}) from {seller_discord_id} for {price}")
                logging.info(f"MARKET: {char_name} bought listing #{listing_id} (Item {template_id}) for {price}.")
                await user.send(self.bot._("✅ **Purchase Complete!** Item delivered to your inventory. Please **relog** to see full artisan bonuses."))
            else:
                logging.error(f"MARKET FAIL: Spawned item {template_id} but could not find it in DB for DNA injection.")
                await user.send(self.bot._("⚠️ Purchase successful, but item synchronization failed. Please contact an admin with Listing ID #{id}.").format(id=listing_id))

        except Exception as e:
            logging.error(f"Critical error during purchase transaction for {char_name}: {e}")
            try: await user.send("❌ A critical error occurred. Please contact an admin.")
            except: pass

    async def _handle_sell(self, char_name, slot, price, server_conf):
        """Extracts item DNA, deletes it from game, and puts it in the market database."""
        db_path = server_conf["DB_PATH"]
        server_name = server_conf["NAME"]
        sync_time = config.MARKETPLACE.get("SYNC_WAIT_SECONDS", 5)

        # 1. Identity Check
        discord_id = find_discord_user_by_char_name(db_path, char_name)
        if not discord_id: return
        
        user = await self.bot.fetch_user(int(discord_id))
        if not user: return

        if price <= 0:
            try: await user.send(self.bot._("❌ Error: Price must be greater than 0."))
            except: pass
            return

        # 2. Inform user and wait for sync
        try:
            await user.send(self.bot._("📦 **Sell Request:** Listing item in slot {slot} for {price} {currency}. Please wait {sync}s...").format(
                slot=slot, price=price, currency=config.MARKETPLACE["CURRENCY_NAME"], sync=sync_time
            ))
        except: pass

        await asyncio.sleep(sync_time)

        # 3. Read Database and Extract DNA
        try:
            char_id = get_char_id_by_name(db_path, char_name)
            if not char_id: return

            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
                query = "SELECT template_id, data FROM item_inventory WHERE owner_id = ? AND item_id = ? AND inv_type = 0"
                row = con.execute(query, (char_id, slot)).fetchone()

            if not row:
                await user.send(self.bot._("❌ Error: Item not found in slot {slot}.").format(slot=slot))
                return

            template_id, blob_data = row
            dna = {"int": {}, "float": {}}
            
            if blob_data:
                packed_id = struct.pack('<I', template_id)
                offset = blob_data.find(packed_id)
                if offset != -1:
                    cursor = offset + 4
                    # Ints
                    prop_count = struct.unpack('<I', blob_data[cursor:cursor+4])[0]
                    cursor += 4
                    for _ in range(prop_count):
                        p_id = struct.unpack('<I', blob_data[cursor:cursor+4])[0]
                        p_val = struct.unpack('<I', blob_data[cursor+4:cursor+8])[0]
                        if p_id not in self.dna_blacklist:
                            dna["int"][p_id] = p_val
                        cursor += 8
                    # Floats
                    if cursor + 4 <= len(blob_data):
                        f_count = struct.unpack('<I', blob_data[cursor:cursor+4])[0]
                        cursor += 4
                        for _ in range(f_count):
                            p_id = struct.unpack('<I', blob_data[cursor:cursor+4])[0]
                            p_val = struct.unpack('<f', blob_data[cursor+4:cursor+8])[0]
                            if p_id not in self.dna_blacklist:
                                dna["float"][p_id] = p_val
                            cursor += 8

            # 4. Remove item from game via RCON
            status_cog = self.bot.get_cog("Status")
            if not status_cog: return

            resp_list, _ = await status_cog.execute_rcon(server_name, "ListPlayers")
            idx = None
            for line in resp_list.splitlines():
                if char_name in line:
                    m = re.search(r"^\s*(\d+)\s*\|", line)
                    if m: idx = m.group(1); break
            
            if idx is None:
                await user.send(self.bot._("❌ You must be online to sell items."))
                return

            # Delete item: Quantity (ID 1) to 0
            await status_cog.execute_rcon(server_name, f"con {idx} SetInventoryItemIntStat {slot} 1 0 0")

            # 5. Save to Marketplace Database
            dna_json = json.dumps(dna)
            with sqlite3.connect(GLOBAL_DB_PATH) as con:
                cur = con.cursor()
                cur.execute(
                    "INSERT INTO market_listings (seller_discord_id, item_template_id, item_dna, price) VALUES (?, ?, ?, ?)",
                    (int(discord_id), template_id, dna_json, price)
                )
                listing_id = cur.lastrowid
                con.commit()

            log_market_action(int(discord_id), "SELL", f"Listed item {template_id} from slot {slot} for {price}. Listing ID: {listing_id}")
            
            await user.send(self.bot._("✅ **Item Listed!**\n🆔 **Listing ID:** {id}\n💰 **Price:** {price} {currency}\n📖 Type `!buy {id}` to purchase (other players).").format(
                id=listing_id, price=price, currency=config.MARKETPLACE["CURRENCY_NAME"]
            ))
            logging.info(f"MARKET: {char_name} listed item {template_id} for {price} (ID: {listing_id})")

        except Exception as e:
            logging.error(f"Critical error in sell for {char_name}: {e}")
            try: await user.send("❌ Internal error during listing.")
            except: pass

    async def _handle_deposit(self, char_name, slot, server_conf):
        """Converts physical currency item in backpack to virtual balance."""
        db_path = server_conf["DB_PATH"]
        server_name = server_conf["NAME"]
        currency_id = config.MARKETPLACE["CURRENCY_ITEM_ID"]
        sync_time = config.MARKETPLACE.get("SYNC_WAIT_SECONDS", 5)
        
        # 1. Identity Check
        discord_id = find_discord_user_by_char_name(db_path, char_name)
        if not discord_id:
            logging.warning(f"Unregistered player {char_name} tried to deposit.")
            return
        
        user = await self.bot.fetch_user(int(discord_id))
        if not user: return

        # 2. Inform user and wait for sync
        try:
            await user.send(self.bot._("💰 **Deposit Request:** Initialized for slot {slot}. Please wait {sync}s for synchronization. **DO NOT MOVE THE ITEM!**").format(slot=slot, sync=sync_time))
        except: pass

        await asyncio.sleep(sync_time)

        # 3. Read Database
        try:
            char_id = get_char_id_by_name(db_path, char_name)
            if not char_id: return

            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
                # Backpack only (inv_type 0)
                query = "SELECT template_id, data FROM item_inventory WHERE owner_id = ? AND item_id = ? AND inv_type = 0"
                row = con.execute(query, (char_id, slot)).fetchone()

            if not row:
                await user.send(self.bot._("❌ Error: No item found in slot {slot}.").format(slot=slot))
                return

            template_id, blob_data = row
            if template_id != currency_id:
                await user.send(self.bot._("❌ Error: Item in slot {slot} is not the accepted currency.").format(slot=slot))
                return

            # 4. Extract Quantity
            quantity = 1
            if blob_data:
                # Find quantity property (ID 1)
                packed_id = struct.pack('<I', template_id)
                offset = blob_data.find(packed_id)
                if offset != -1:
                    cursor = offset + 4
                    prop_count = struct.unpack('<I', blob_data[cursor:cursor+4])[0]
                    cursor += 4
                    for _ in range(prop_count):
                        p_id = struct.unpack('<I', blob_data[cursor:cursor+4])[0]
                        p_val = struct.unpack('<I', blob_data[cursor+4:cursor+8])[0]
                        if p_id == 1:
                            quantity = p_val
                            break
                        cursor += 8

            # 5. Execute Transaction (RCON)
            status_cog = self.bot.get_cog("Status")
            if not status_cog: return

            # Get player index
            resp_list, _ = await status_cog.execute_rcon(server_name, "ListPlayers")
            idx = None
            for line in resp_list.splitlines():
                if char_name in line:
                    m = re.search(r"^\s*(\d+)\s*\|", line)
                    if m: idx = m.group(1); break
            
            if idx is None:
                await user.send(self.bot._("❌ You must be online to deposit."))
                return

            # A. Delete physical item (Quantity to 0)
            # con X SetInventoryItemIntStat slot statID value inv_type
            await status_cog.execute_rcon(server_name, f"con {idx} SetInventoryItemIntStat {slot} 1 0 0")
            
            # B. Update Virtual Balance
            if update_player_balance(int(discord_id), quantity):
                log_market_action(int(discord_id), "DEPOSIT", f"Deposited {quantity} of item {template_id} from slot {slot}")
                new_balance = get_player_balance(int(discord_id))
                await user.send(self.bot._("✅ **Deposit Successful!**\n📥 **Amount:** {qty}\n💰 **New Balance:** {balance} {currency}").format(
                    qty=quantity, balance=new_balance, currency=config.MARKETPLACE["CURRENCY_NAME"]
                ))
                logging.info(f"MARKET: {char_name} deposited {quantity} coins.")
            else:
                await user.send("❌ Internal database error during deposit.")

        except Exception as e:
            logging.error(f"Critical error in deposit for {char_name}: {e}")

async def setup(bot):
    await bot.add_cog(MarketplaceCog(bot))
