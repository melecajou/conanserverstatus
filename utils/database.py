import sqlite3
import logging
import os
from typing import Dict, List, Any, Optional

# --- DATABASE SETUP ---
DEFAULT_PLAYER_TRACKER_DB = "data/playertracker.db"
GLOBAL_DB_PATH = "data/global_registry.db"


def initialize_global_db(db_path: str = GLOBAL_DB_PATH):
    """Creates or updates the global registry database."""
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()

            # Table: User Identities (Platform ID -> Discord ID)
            cur.execute(
                """
            CREATE TABLE IF NOT EXISTS user_identities (
                platform_id TEXT PRIMARY KEY,
                discord_id INTEGER NOT NULL
            )
        """
            )

            # Table: Discord VIPs (Discord ID -> VIP Level & Expiry)
            cur.execute(
                """
            CREATE TABLE IF NOT EXISTS discord_vips (
                discord_id INTEGER PRIMARY KEY,
                vip_level INTEGER DEFAULT 0,
                vip_expiry_date TEXT
            )
        """
            )

            # Table: Player Wallets (Virtual Currency)
            cur.execute(
                """
            CREATE TABLE IF NOT EXISTS player_wallets (
                discord_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0
            )
        """
            )

            # Table: Market Listings (Items in custody)
            cur.execute(
                """
            CREATE TABLE IF NOT EXISTS market_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_discord_id INTEGER NOT NULL,
                item_template_id INTEGER NOT NULL,
                item_dna TEXT NOT NULL, -- JSON string containing all properties
                price INTEGER NOT NULL,
                status TEXT DEFAULT 'active', -- active, sold, canceled, delivered
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
            )

            # Table: Market Audit Log
            cur.execute(
                """
            CREATE TABLE IF NOT EXISTS market_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                discord_id INTEGER,
                action TEXT, -- DEPOSIT, SELL, BUY, CANCEL
                details TEXT
            )
        """
            )
            con.commit()
        logging.info(f"Global registry database '{db_path}' initialized successfully.")
    except Exception as e:
        logging.critical(
            f"Failed to initialize global registry database '{db_path}': {e}"
        )


def migrate_to_global_db(server_dbs: List[str], global_db_path: str = GLOBAL_DB_PATH):
    """Migrates existing registration and VIP data to the global database."""
    try:
        with sqlite3.connect(global_db_path) as global_con:
            global_cur = global_con.cursor()

            for db_path in server_dbs:
                if not os.path.exists(db_path):
                    continue

                try:
                    with sqlite3.connect(
                        f"file:{db_path}?mode=ro", uri=True
                    ) as local_con:
                        local_cur = local_con.cursor()

                        # Check columns exist
                        local_cur.execute("PRAGMA table_info(player_time)")
                        columns = [info[1] for info in local_cur.fetchall()]
                        has_discord = "discord_id" in columns
                        has_vip = "vip_level" in columns
                        has_expiry = "vip_expiry_date" in columns

                        if not has_discord:
                            continue

                        # Migrate Identities
                        local_cur.execute(
                            "SELECT platform_id, discord_id FROM player_time WHERE discord_id IS NOT NULL AND discord_id != ''"
                        )
                        for platform_id, discord_id in local_cur.fetchall():
                            if discord_id:
                                try:
                                    global_cur.execute(
                                        "INSERT OR IGNORE INTO user_identities (platform_id, discord_id) VALUES (?, ?)",
                                        (platform_id, int(discord_id)),
                                    )
                                except ValueError:
                                    continue

                        # Migrate VIPs (Take the highest level found)
                        if has_vip:
                            query = "SELECT discord_id, vip_level"
                            if has_expiry:
                                query += ", vip_expiry_date"
                            else:
                                query += ", NULL"
                            query += " FROM player_time WHERE discord_id IS NOT NULL AND discord_id != '' AND vip_level > 0"

                            local_cur.execute(query)
                            for (
                                discord_id_raw,
                                vip_level,
                                vip_expiry,
                            ) in local_cur.fetchall():
                                try:
                                    discord_id = int(discord_id_raw)
                                except ValueError:
                                    continue

                                # Check existing VIP level
                                global_cur.execute(
                                    "SELECT vip_level FROM discord_vips WHERE discord_id = ?",
                                    (discord_id,),
                                )
                                row = global_cur.fetchone()
                                if row:
                                    if vip_level > row[0]:
                                        global_cur.execute(
                                            "UPDATE discord_vips SET vip_level = ?, vip_expiry_date = ? WHERE discord_id = ?",
                                            (vip_level, vip_expiry, discord_id),
                                        )
                                else:
                                    global_cur.execute(
                                        "INSERT INTO discord_vips (discord_id, vip_level, vip_expiry_date) VALUES (?, ?, ?)",
                                        (discord_id, vip_level, vip_expiry),
                                    )

                except Exception as e:
                    logging.error(f"Error reading from {db_path} during migration: {e}")

            global_con.commit()
            logging.info("Migration to global database completed.")

    except Exception as e:
        logging.error(f"Failed to migrate to global database: {e}")


def get_global_player_data(
    platform_ids: List[str], global_db_path: str = GLOBAL_DB_PATH
) -> Dict[str, Dict[str, Any]]:
    """
    Fetches registration and VIP data for a batch of platform IDs from the global database.
    """
    data = {
        pid: {"discord_id": None, "vip_level": 0, "vip_expiry": None}
        for pid in platform_ids
    }
    if not platform_ids:
        return data

    try:
        with sqlite3.connect(f"file:{global_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            placeholders = ", ".join("?" * len(platform_ids))

            query = f"""
                SELECT ui.platform_id, ui.discord_id, dv.vip_level, dv.vip_expiry_date
                FROM user_identities ui
                LEFT JOIN discord_vips dv ON ui.discord_id = dv.discord_id
                WHERE ui.platform_id IN ({placeholders})
            """
            cur.execute(query, platform_ids)
            for pid, discord_id, vip_level, vip_expiry in cur.fetchall():
                data[pid] = {
                    "discord_id": discord_id,
                    "vip_level": vip_level if vip_level else 0,
                    "vip_expiry": vip_expiry,
                }
    except Exception as e:
        logging.error(f"Error fetching global player data: {e}")
    return data


def link_discord_to_platform(
    platform_id: str, discord_id: int, global_db_path: str = GLOBAL_DB_PATH
) -> bool:
    """Links a platform ID to a Discord ID in the global registry."""
    try:
        with sqlite3.connect(global_db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO user_identities (platform_id, discord_id) VALUES (?, ?)",
                (platform_id, discord_id),
            )
            con.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to link platform to discord in global db: {e}")
        return False


def set_global_vip(
    discord_id: int,
    vip_level: int,
    expiry: str = None,
    global_db_path: str = GLOBAL_DB_PATH,
) -> bool:
    """Sets the VIP level for a Discord user globally."""
    try:
        with sqlite3.connect(global_db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO discord_vips (discord_id, vip_level, vip_expiry_date) VALUES (?, ?, ?)",
                (discord_id, vip_level, expiry),
            )
            con.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to set global VIP: {e}")
        return False


def get_global_vip(
    discord_id: int, global_db_path: str = GLOBAL_DB_PATH
) -> Optional[Dict[str, Any]]:
    """Retrieves VIP data for a specific Discord ID."""
    try:
        with sqlite3.connect(f"file:{global_db_path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(
                "SELECT vip_level, vip_expiry_date FROM discord_vips WHERE discord_id = ?",
                (discord_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "vip_level": row["vip_level"],
                    "vip_expiry": row["vip_expiry_date"],
                }
    except Exception as e:
        logging.error(f"Error fetching global VIP for {discord_id}: {e}")
    return None


def get_all_vips(global_db_path: str = GLOBAL_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves all VIP users from the global registry."""
    vips = []
    try:
        with sqlite3.connect(f"file:{global_db_path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(
                "SELECT discord_id, vip_level, vip_expiry_date FROM discord_vips WHERE vip_level > 0"
            )
            for row in cur.fetchall():
                vips.append(
                    {
                        "discord_id": row["discord_id"],
                        "vip_level": row["vip_level"],
                        "vip_expiry": row["vip_expiry_date"],
                    }
                )
    except Exception as e:
        logging.error(f"Error fetching all vips: {e}")
    return vips


def update_vip_expiry(
    discord_id: int, days: int, global_db_path: str = GLOBAL_DB_PATH
) -> bool:
    """Updates only the expiration date for an existing VIP user."""
    try:
        from datetime import datetime, timedelta

        expiry_dt = datetime.now() + timedelta(days=days)
        expiry_date = expiry_dt.isoformat()

        with sqlite3.connect(global_db_path) as con:
            cur = con.cursor()
            # Check if user exists first
            cur.execute(
                "SELECT 1 FROM discord_vips WHERE discord_id = ?", (discord_id,)
            )
            if not cur.fetchone():
                return False

            cur.execute(
                "UPDATE discord_vips SET vip_expiry_date = ? WHERE discord_id = ?",
                (expiry_date, discord_id),
            )
            con.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to update VIP expiry: {e}")
        return False


def initialize_player_tracker_db(db_path: str):
    """Creates or updates the player tracker database and table."""
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS player_time (
                platform_id TEXT NOT NULL,
                server_name TEXT NOT NULL,
                online_minutes INTEGER DEFAULT 0,
                last_rewarded_hour INTEGER DEFAULT 0,
                PRIMARY KEY (platform_id, server_name)
            )
        """
        )
        cur.execute("PRAGMA table_info(player_time)")
        columns = [info[1] for info in cur.fetchall()]
        if "discord_id" not in columns:
            cur.execute("ALTER TABLE player_time ADD COLUMN discord_id TEXT")
        if "vip_level" not in columns:
            cur.execute(
                "ALTER TABLE player_time ADD COLUMN vip_level INTEGER DEFAULT 0"
            )
        if "vip_expiry_date" not in columns:
            cur.execute("ALTER TABLE player_time ADD COLUMN vip_expiry_date TEXT")
        if "last_reward_playtime" not in columns:
            cur.execute(
                "ALTER TABLE player_time ADD COLUMN last_reward_playtime INTEGER DEFAULT 0"
            )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS player_homes (
                platform_id TEXT NOT NULL,
                server_name TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                z REAL NOT NULL,
                PRIMARY KEY (platform_id, server_name)
            )
        """
        )
        con.commit()
        con.close()
        logging.info(
            f"Player tracker database '{db_path}' initialized/updated successfully."
        )
    except Exception as e:
        logging.critical(
            f"Failed to initialize player tracker database '{db_path}': {e}"
        )


def get_batch_player_levels(
    db_path: str, char_names: List[str]
) -> Optional[Dict[str, int]]:
    """Queries the game database to get the levels for a batch of characters."""
    levels = {name: 0 for name in char_names}
    if not db_path or not char_names:
        return levels
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            placeholders = ", ".join("?" * len(char_names))
            cur.execute(
                f"SELECT char_name, level FROM characters WHERE char_name IN ({placeholders})",
                char_names,
            )
            for name, level in cur.fetchall():
                levels[name] = level
    except sqlite3.DatabaseError:
        return None
    except Exception as e:
        logging.error(f"Could not read batch player levels from {db_path}: {e}")
        return None
    return levels


def get_batch_player_data(
    db_path: str, platform_ids: List[str], server_name: str
) -> Dict[str, Dict[str, Any]]:
    """Queries the player tracker database to get data for a batch of players."""
    player_data = {
        pid: {"online_minutes": 0, "is_registered": False} for pid in platform_ids
    }
    if not platform_ids:
        return player_data
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            placeholders = ", ".join("?" * len(platform_ids))
            query_params = platform_ids + [server_name]
            cur.execute(
                f"SELECT platform_id, online_minutes, discord_id FROM player_time WHERE platform_id IN ({placeholders}) AND server_name = ?",
                query_params,
            )
            for pid, minutes, discord_id in cur.fetchall():
                player_data[pid]["online_minutes"] = minutes
                player_data[pid]["is_registered"] = bool(discord_id)
    except Exception as e:
        logging.error(f"Could not read batch player data from {db_path}: {e}")
    return player_data


def link_discord_to_character(
    player_tracker_db_path: str,
    game_db_path: str,
    server_name: str,
    discord_id: int,
    char_name: str,
) -> bool:
    """Links a Discord ID to a character by finding their platform_id through the game.db."""

    # Esta variável 'account_id' estava sendo usada incorretamente.
    # Agora vamos buscar o 'player_id_text' (ex: 'DE70F14C9A560DD3')
    player_id_text = None
    platform_id = None

    try:
        with sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()

            # --- ETAPA 1 CORRIGIDA ---
            # Em vez de 'id', selecionamos 'playerId'
            cur.execute(
                "SELECT playerId FROM characters WHERE char_name = ?", (char_name,)
            )
            result = cur.fetchone()
            if result:
                player_id_text = result[0]  # Este é o ID de texto da conta

                # --- ETAPA 2 CORRIGIDA ---
                # Usamos 'player_id_text' para procurar na coluna 'user' da tabela 'account'
                cur.execute(
                    "SELECT platformId FROM account WHERE id = ?", (player_id_text,)
                )
                result2 = cur.fetchone()
                if result2:
                    platform_id = result2[0]  # Este é o SteamID (ou ID de plataforma)

    except Exception as e:
        logging.error(f"Could not read character data from {game_db_path}: {e}")
        return False

    if not platform_id:
        # A mensagem de log original estava correta, mas a lógica para chegar aqui estava errada.
        logging.warning(
            f"Could not find a valid platform_id for character '{char_name}'. (playerId: {player_id_text})"
        )
        return False

    # A Etapa 3 (salvar no nosso DB) estava correta e permanece a mesma.
    try:
        with sqlite3.connect(player_tracker_db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO player_time (platform_id, server_name) VALUES (?, ?)",
                (platform_id, server_name),
            )
            cur.execute(
                "UPDATE player_time SET discord_id = ? WHERE platform_id = ? AND server_name = ?",
                (str(discord_id), platform_id, server_name),
            )
            con.commit()

        return True
    except Exception as e:
        logging.error(
            f"Failed to link Discord ID to character in {player_tracker_db_path}: {e}"
        )
        return False


def save_player_home(
    db_path: str, platform_id: str, server_name: str, x: float, y: float, z: float
) -> bool:
    """Saves or updates a player's home coordinates."""
    try:
        with sqlite3.connect(db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO player_homes (platform_id, server_name, x, y, z) VALUES (?, ?, ?, ?, ?)",
                (platform_id, server_name, x, y, z),
            )
            con.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to save player home in {db_path}: {e}")
        return False


def get_player_home(db_path: str, platform_id: str, server_name: str) -> Any:
    """Retrieves a player's home coordinates."""
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            cur.execute(
                "SELECT x, y, z FROM player_homes WHERE platform_id = ? AND server_name = ?",
                (platform_id, server_name),
            )
            return cur.fetchone()
    except Exception as e:
        logging.error(f"Failed to get player home from {db_path}: {e}")
        return None


def get_character_coordinates(game_db_path: str, char_name: str) -> Any:
    """Gets the current coordinates of a character from the game database."""
    if not os.path.exists(game_db_path):
        return None
    try:
        with sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            # Join characters and actor_position on characters.id = actor_position.id
            cur.execute(
                """
                SELECT ap.x, ap.y, ap.z 
                FROM characters c 
                JOIN actor_position ap ON c.id = ap.id 
                WHERE c.char_name = ?
                """,
                (char_name,),
            )
            return cur.fetchone()
    except Exception as e:
        logging.error(f"Failed to get character coordinates from {game_db_path}: {e}")
        return None


def get_all_guild_members(
    server_dbs: List[str], global_db_path: str = GLOBAL_DB_PATH
) -> Optional[Dict[int, List[str]]]:
    """
    Scans all server databases to find guild affiliations for registered Discord users.
    Returns: {discord_id: [list_of_guild_names]} or None if a DB read failed.
    """
    # 1. Load all registered users (Platform ID -> Discord ID)
    registered_users = {}
    try:
        with sqlite3.connect(f"file:{global_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            cur.execute("SELECT platform_id, discord_id FROM user_identities")
            for pid, did in cur.fetchall():
                registered_users[pid] = did
    except Exception as e:
        logging.error(f"Failed to load registered users for guild sync: {e}")
        return None

    user_guilds = {}  # {discord_id: set(guild_names)}

    # 2. Scan each game DB
    for db_path in server_dbs:
        if not db_path or not os.path.exists(db_path):
            continue

        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
                cur = con.cursor()
                # Join characters, guilds, and account to get PlatformID + GuildName
                query = """
                    SELECT a.platformId, g.name 
                    FROM characters c 
                    JOIN guilds g ON c.guild = g.guildId 
                    JOIN account a ON c.playerId = a.id
                """
                cur.execute(query)

                for platform_id, guild_name in cur.fetchall():
                    if platform_id in registered_users:
                        discord_id = registered_users[platform_id]
                        if discord_id not in user_guilds:
                            user_guilds[discord_id] = set()
                        user_guilds[discord_id].add(guild_name)

        except sqlite3.DatabaseError as e:
            # Critical: If we can't read a DB, we can't trust the "absence" of a guild.
            # Abort the entire operation to prevent role deletion.
            logging.error(
                f"Critical error reading guilds from {db_path}: {e} (Aborting Sync)"
            )
            return None
        except Exception as e:
            logging.error(f"Error reading guilds from {db_path}: {e}")
            return None

    # Convert sets to lists
    return {k: list(v) for k, v in user_guilds.items()}


def get_inactive_structures(
    game_db_path: str, sql_path: str, days: int
) -> List[Dict[str, Any]]:
    """
    Identifies inactive building structures based on an SQL script.
    """
    if not os.path.exists(game_db_path) or not os.path.exists(sql_path):
        return []

    results = []
    try:
        with open(sql_path, "r") as f:
            query = f.read()

        with sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute(query, (days,))
            for row in cur.fetchall():
                results.append(
                    {
                        "owner": row["Owner"],
                        "pieces": row["Pieces"],
                        "location": row["Location"],
                        "last_activity": row["LastActivity_GMT3"],
                    }
                )
    except Exception as e:
        logging.error(f"Error fetching inactivity structures from {game_db_path}: {e}")

    return results


def find_discord_user_by_char_name(
    game_db_path: str, char_name: str, global_db_path: str = GLOBAL_DB_PATH
) -> Optional[int]:
    """
    Searches for a character name in the game DB and returns the linked Discord ID if found.
    """
    if not os.path.exists(game_db_path):
        return None

    try:
        with sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            query = """
                SELECT a.platformId 
                FROM characters c
                JOIN account a ON c.playerId = a.id
                WHERE c.char_name LIKE ?
                LIMIT 1
            """
            cur.execute(query, (f"%{char_name}%",))
            row = cur.fetchone()

            if row:
                platform_id = row[0]
                # Check global registry
                with sqlite3.connect(
                    f"file:{global_db_path}?mode=ro", uri=True
                ) as g_con:
                    g_cur = g_con.cursor()
                    g_cur.execute(
                        "SELECT discord_id FROM user_identities WHERE platform_id = ?",
                        (platform_id,),
                    )
                    res = g_cur.fetchone()
                    if res:
                        return res[0]
    except Exception as e:
        logging.error(f"Error searching for user by char name in {game_db_path}: {e}")

    return None


def get_char_id_by_name(db_path: str, char_name: str) -> Optional[int]:
    """Retrieves the internal character ID from the game database."""
    if not os.path.exists(db_path):
        return None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM characters WHERE char_name = ?", (char_name,))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as e:
        logging.error(f"Error getting char_id for {char_name}: {e}")
        return None


def get_player_balance(discord_id: int, global_db_path: str = GLOBAL_DB_PATH) -> int:
    """Retrieves the virtual currency balance for a player."""
    try:
        with sqlite3.connect(f"file:{global_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            cur.execute(
                "SELECT balance FROM player_wallets WHERE discord_id = ?", (discord_id,)
            )
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logging.error(f"Error fetching balance for {discord_id}: {e}")
        return 0


def update_player_balance(
    discord_id: int, amount: int, global_db_path: str = GLOBAL_DB_PATH
) -> bool:
    """Adds (positive) or subtracts (negative) from a player's virtual balance."""
    try:
        with sqlite3.connect(global_db_path) as con:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO player_wallets (discord_id, balance) 
                VALUES (?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET balance = balance + excluded.balance
                """,
                (discord_id, amount),
            )
            con.commit()
        return True
    except Exception as e:
        logging.error(f"Failed to update balance for {discord_id}: {e}")
        return False


def log_market_action(
    discord_id: int, action: str, details: str, global_db_path: str = GLOBAL_DB_PATH
):
    """Logs a marketplace transaction or wallet action for auditing."""
    try:
        with sqlite3.connect(global_db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO market_audit_log (discord_id, action, details) VALUES (?, ?, ?)",
                (discord_id, action, details),
            )
            con.commit()
    except Exception as e:
        logging.error(f"Failed to log market action: {e}")


def get_item_in_backpack(
    db_path: str, char_id: int, template_id: int
) -> Optional[Dict[str, Any]]:
    """
    Searches for a specific item ID in a player's backpack (inv_type 0).
    Returns a dictionary with 'slot' and 'quantity' or None if not found.
    """
    import struct

    if not os.path.exists(db_path):
        return None

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            # inv_type 0 is Backpack
            query = "SELECT item_id, data FROM item_inventory WHERE owner_id = ? AND template_id = ? AND inv_type = 0"
            cur.execute(query, (char_id, template_id))
            rows = cur.fetchall()

            for slot, data in rows:
                quantity = 1
                if data:
                    try:
                        packed_id = struct.pack("<I", template_id)
                        offset = data.find(packed_id)
                        while offset != -1:
                            cursor_pos = offset + 4
                            if cursor_pos + 4 <= len(data):
                                prop_count = struct.unpack(
                                    "<I", data[cursor_pos : cursor_pos + 4]
                                )[0]
                                cursor_pos += 4
                                if prop_count < 100:
                                    if cursor_pos + (prop_count * 8) <= len(data):
                                        for _ in range(prop_count):
                                            prop_id = struct.unpack(
                                                "<I", data[cursor_pos : cursor_pos + 4]
                                            )[0]
                                            cursor_pos += 4
                                            prop_val = struct.unpack(
                                                "<I", data[cursor_pos : cursor_pos + 4]
                                            )[0]
                                            cursor_pos += 4
                                            if prop_id == 1:  # 1 is Quantity
                                                quantity = prop_val
                                                break
                                offset = data.find(packed_id, offset + 1)
                    except:
                        pass

                # Return the first slot found with the item
                return {"slot": slot, "quantity": quantity}

    except Exception as e:
        logging.error(f"Error reading item from backpack in {db_path}: {e}")

    return None
