import os
import sqlite3
import json
import logging
import sys
from datetime import datetime

# Adiciona o diretório raiz ao path para importar o config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Configurações
DEATH_EVENT_TYPE = 103
RANKING_DB = getattr(config, "KILLFEED_RANKING_DB", "data/killfeed/ranking.db")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def reset_ranking_db():
    logging.info(f"Resetando o banco de dados de ranking: {RANKING_DB}")
    if os.path.exists(RANKING_DB):
        os.remove(RANKING_DB)

    os.makedirs(os.path.dirname(RANKING_DB), exist_ok=True)
    con = sqlite3.connect(RANKING_DB)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            server_name TEXT,
            player_name TEXT,
            kills INTEGER DEFAULT 0,
            deaths INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (server_name, player_name)
        )
    """)
    con.commit()
    con.close()


def update_player_score(server_name, killer_name, victim_name):
    try:
        con = sqlite3.connect(RANKING_DB)
        cur = con.cursor()

        # Killer
        cur.execute(
            "INSERT OR IGNORE INTO scores (server_name, player_name) VALUES (?, ?)",
            (server_name, killer_name),
        )
        cur.execute(
            "UPDATE scores SET kills = kills + 1, score = score + 1 WHERE server_name = ? AND player_name = ?",
            (server_name, killer_name),
        )

        # Victim
        cur.execute(
            "INSERT OR IGNORE INTO scores (server_name, player_name) VALUES (?, ?)",
            (server_name, victim_name),
        )
        cur.execute(
            "UPDATE scores SET deaths = deaths + 1, score = score - 1 WHERE server_name = ? AND player_name = ?",
            (server_name, victim_name),
        )

        con.commit()
        con.close()
    except sqlite3.Error as e:
        logging.error(f"Erro ao atualizar score: {e}")


def recalculate():
    reset_ranking_db()

    for server_conf in config.SERVERS:
        server_name = server_conf["NAME"]
        kf_config = server_conf.get("KILLFEED_CONFIG")

        if not kf_config or not kf_config.get("ENABLED"):
            logging.info(f"Killfeed desativado para o servidor: {server_name}")
            continue

        db_path = server_conf.get("DB_PATH")
        if not db_path or not os.path.exists(db_path):
            logging.warning(
                f"Banco de dados não encontrado para {server_name}: {db_path}"
            )
            continue

        logging.info(f"Processando servidor: {server_name}")
        last_death_times = {}
        max_event_time = 0

        try:
            db_uri = f"file:{os.path.abspath(db_path)}?mode=ro"
            con = sqlite3.connect(db_uri, uri=True)
            cur = con.cursor()

            query = f"SELECT worldTime, causerName, ownerName FROM game_events WHERE eventType = {DEATH_EVENT_TYPE} ORDER BY worldTime ASC"

            kills_count = 0
            for event_time, killer, victim in cur.execute(query):
                if victim:
                    last_death = last_death_times.get(victim, 0)
                    if event_time - last_death < 10:
                        continue
                    last_death_times[victim] = event_time

                if killer and victim and killer != victim:
                    update_player_score(server_name, killer, victim)
                    kills_count += 1

                if event_time > max_event_time:
                    max_event_time = event_time

            con.close()
            logging.info(
                f"Finalizado {server_name}: {kills_count} abates PvP processados."
            )

            # Atualiza o arquivo de último evento para o bot continuar daqui
            last_event_file = kf_config.get("LAST_EVENT_FILE")
            if last_event_file and max_event_time > 0:
                os.makedirs(
                    os.path.dirname(os.path.abspath(last_event_file)), exist_ok=True
                )
                with open(last_event_file, "w") as f:
                    f.write(str(max_event_time))
                logging.info(
                    f"Arquivo de sincronização atualizado para {server_name}: {max_event_time}"
                )

        except Exception as e:
            logging.error(f"Erro ao processar {server_name}: {e}")


if __name__ == "__main__":
    print(
        "Este script irá ZERAR o ranking atual e recalcular tudo com base nos game.db de cada servidor."
    )
    confirm = input("Tem certeza que deseja continuar? (sim/não): ")
    if confirm.lower() == "sim":
        recalculate()
        print("\nRecálculo concluído com sucesso!")
    else:
        print("Operação cancelada.")
