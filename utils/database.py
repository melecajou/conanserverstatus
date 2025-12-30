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
                            for discord_id_raw, vip_level, vip_expiry in local_cur.fetchall():
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
    data = {pid: {"discord_id": None, "vip_level": 0, "vip_expiry": None} for pid in platform_ids}
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
                    "vip_expiry": vip_expiry
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
    discord_id: int, vip_level: int, expiry: str = None, global_db_path: str = GLOBAL_DB_PATH
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


def get_batch_player_levels(db_path: str, char_names: List[str]) -> Optional[Dict[str, int]]:
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


def save_player_home(db_path: str, platform_id: str, server_name: str, x: float, y: float, z: float) -> bool:
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


def get_all_guild_members(server_dbs: List[str], global_db_path: str = GLOBAL_DB_PATH) -> Optional[Dict[int, List[str]]]:
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

    user_guilds = {} # {discord_id: set(guild_names)}

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
            logging.error(f"Critical error reading guilds from {db_path}: {e} (Aborting Sync)")
            return None
        except Exception as e:
            logging.error(f"Error reading guilds from {db_path}: {e}")
            return None

    # Convert sets to lists
    return {k: list(v) for k, v in user_guilds.items()}
