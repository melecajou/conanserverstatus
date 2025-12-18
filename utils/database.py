import sqlite3
import logging
import os
from typing import Dict, List, Any

# --- DATABASE SETUP ---
DEFAULT_PLAYER_TRACKER_DB = "data/playertracker.db"


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
        con.commit()
        con.close()
        logging.info(
            f"Player tracker database '{db_path}' initialized/updated successfully."
        )
    except Exception as e:
        logging.critical(
            f"Failed to initialize player tracker database '{db_path}': {e}"
        )


def get_batch_player_levels(db_path: str, char_names: List[str]) -> Dict[str, int]:
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
    except Exception as e:
        logging.error(f"Could not read batch player levels from {db_path}: {e}")
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
