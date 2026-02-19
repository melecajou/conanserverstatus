import discord
from discord.ext import commands, tasks
import sqlite3
import os
import glob
from datetime import datetime
import json
import logging
import asyncio

import config

# --- Constants ---
DEATH_EVENT_TYPE = 103


class KillfeedCog(commands.Cog, name="Killfeed"):
    """Handles in-game death announcements and PvP rankings."""

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        # Cooldown/Duplicate check: {server_name: {victim_name: last_death_time}}
        self.last_death_times = {}
        # Cursor storage for state (message IDs)
        self.ranking_state = self._load_ranking_state()

        # Start tasks
        self.kill_check_task.start()
        self.ranking_update_task.start()
        self.unified_ranking_task.start()

    def cog_unload(self):
        self.kill_check_task.cancel()
        self.ranking_update_task.cancel()
        self.unified_ranking_task.cancel()

    def _load_ranking_state(self):
        state_file = getattr(
            config, "KILLFEED_STATE_FILE", "data/killfeed/ranking_state.json"
        )
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_ranking_state(self):
        state_file = getattr(
            config, "KILLFEED_STATE_FILE", "data/killfeed/ranking_state.json"
        )
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(self.ranking_state, f, indent=4)

    def _get_last_event_time(self, file_path):
        abs_path = os.path.abspath(file_path)
        try:
            with open(abs_path, "r") as f:
                val = int(f.read().strip())
                logging.debug(f"[Killfeed] Read last event time {val} from {abs_path}")
                return val
        except (FileNotFoundError, ValueError):
            logging.warning(
                f"[Killfeed] Could not read last event time from {abs_path}. Defaulting to 0."
            )
            return 0

    def _set_last_event_time(self, new_time, file_path):
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w") as f:
            f.write(str(new_time))
        logging.debug(f"[Killfeed] Saved new last event time {new_time} to {abs_path}")

    async def _update_player_score(self, server_name, killer_name, victim_name):
        try:
            db_path = getattr(config, "KILLFEED_RANKING_DB", "data/killfeed/ranking.db")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            con = sqlite3.connect(db_path)
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
            cur.execute(
                "INSERT OR IGNORE INTO scores (server_name, player_name) VALUES (?, ?)",
                (server_name, killer_name),
            )
            cur.execute(
                "UPDATE scores SET kills = kills + 1, score = score + 1 WHERE server_name = ? AND player_name = ?",
                (server_name, killer_name),
            )
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
            logging.error(f"ERROR [Killfeed - Ranking]: Failed to update score: {e}")

    @tasks.loop(seconds=20)
    async def kill_check_task(self):
        """Periodically checks all servers for new death events."""
        for server_conf in config.SERVERS:
            kf_config = server_conf.get("KILLFEED_CONFIG")
            if not kf_config or not kf_config.get("ENABLED"):
                continue
            try:
                await self._process_server_kills(server_conf)
            except Exception as e:
                logging.error(f"Error checking kills for {server_conf['NAME']}: {e}")

    async def _process_server_kills(self, server_conf):
        server_name = server_conf["NAME"]
        kf_config = server_conf["KILLFEED_CONFIG"]
        channel = self.bot.get_channel(kf_config["CHANNEL_ID"])
        if not channel:
            return

        db_path = server_conf.get("DB_PATH")
        if not db_path or not os.path.exists(db_path):
            return

        last_time = self._get_last_event_time(kf_config["LAST_EVENT_FILE"])
        new_max_time = last_time

        logging.debug(
            f"[Killfeed] Checking kills for {server_name} since timestamp {last_time}..."
        )

        try:
            # Simplificando a conexão para evitar o erro 'unable to open database file'
            # Usando apenas o caminho direto com o prefixo file: e mode=ro
            db_uri = f"file:{os.path.abspath(db_path)}?mode=ro"
            con = sqlite3.connect(db_uri, uri=True)
            cur = con.cursor()

            spawns_db = getattr(config, "KILLFEED_SPAWNS_DB", "data/killfeed/spawns.db")
            has_spawns = False
            if os.path.exists(spawns_db):
                try:
                    cur.execute(
                        f"ATTACH DATABASE '{os.path.abspath(spawns_db)}' AS spawns_db;"
                    )
                    # Verifica se a tabela spawns existe no banco anexado
                    cur.execute(
                        "SELECT 1 FROM spawns_db.sqlite_master WHERE type='table' AND name='spawns'"
                    )
                    if cur.fetchone():
                        has_spawns = True
                except Exception as e:
                    logging.error(f"Failed to attach or verify spawns_db: {e}")

            if has_spawns:
                query = f"""
                    WITH events AS (
                        SELECT
                            worldTime,
                            causerName,
                            ownerName,
                            json_extract(argsMap, '$.nonPersistentCauser') AS npc_id
                        FROM game_events
                        WHERE worldTime > ? AND eventType = {DEATH_EVENT_TYPE}
                    )
                    SELECT e.worldTime, e.causerName, e.ownerName, e.npc_id, s.Name
                    FROM events e
                    LEFT JOIN spawns_db.spawns s ON s.RowName = e.npc_id
                    ORDER BY e.worldTime ASC
                """
            else:
                query = f"""
                    SELECT
                        worldTime,
                        causerName,
                        ownerName,
                        json_extract(argsMap, '$.nonPersistentCauser') AS npc_id,
                        NULL as npc_name
                    FROM game_events
                    WHERE worldTime > ? AND eventType = {DEATH_EVENT_TYPE}
                    ORDER BY worldTime ASC
                """

            # Fetch all results to avoid cursor reuse issues and improve safety
            results = cur.execute(query, (last_time,)).fetchall()

            for event_time, killer, victim, npc_id, npc_name_from_db in results:
                if event_time > new_max_time:
                    new_max_time = event_time

                if victim:
                    if server_name not in self.last_death_times:
                        self.last_death_times[server_name] = {}
                    last_death = self.last_death_times[server_name].get(victim, 0)
                    if event_time - last_death < 10:
                        continue
                    self.last_death_times[server_name][victim] = event_time

                is_pvp_kill = bool(killer and victim and killer != victim)
                if is_pvp_kill:
                    await self._update_player_score(server_name, killer, victim)

                if kf_config.get("PVP_ONLY") and not is_pvp_kill:
                    continue

                if is_pvp_kill:
                    message = self.bot._("💀 **{killer}** killed **{victim}**!").format(
                        killer=killer, victim=victim
                    )
                elif victim:
                    npc_name = npc_name_from_db if npc_name_from_db else self.bot._("the environment")
                    message = self.bot._(
                        "☠️ **{victim}** was killed by **{npc}**!"
                    ).format(victim=victim, npc=npc_name)
                else:
                    continue

                embed = discord.Embed(
                    description=message, color=discord.Color.dark_red()
                )
                embed.set_footer(
                    text=self.bot._("📍 {server} | {date}").format(
                        server=server_name,
                        date=datetime.fromtimestamp(event_time).strftime(
                            "%d/%m/%Y %H:%M:%S"
                        ),
                    )
                )
                await channel.send(embed=embed)

            con.close()
            if new_max_time > last_time:
                self._set_last_event_time(new_max_time, kf_config["LAST_EVENT_FILE"])
        except sqlite3.Error as e:
            logging.error(f"Killfeed DB Error for {server_name}: {e}")
        except Exception as e:
            logging.error(f"Killfeed Unexpected Error for {server_name}: {e}")

    @tasks.loop(minutes=5)
    async def ranking_update_task(self):
        """Updates individual server ranking messages."""
        for server_conf in config.SERVERS:
            kf_config = server_conf.get("KILLFEED_CONFIG")
            if not kf_config or not kf_config.get("ENABLED"):
                continue
            try:
                await self._update_server_ranking(server_conf)
            except Exception as e:
                logging.error(f"Error updating ranking for {server_conf['NAME']}: {e}")

    async def _update_server_ranking(self, server_conf):
        server_name = server_conf["NAME"]
        kf_config = server_conf["KILLFEED_CONFIG"]
        channel = self.bot.get_channel(kf_config["RANKING_CHANNEL_ID"])
        if not channel:
            return

        db_path = getattr(config, "KILLFEED_RANKING_DB", "data/killfeed/ranking.db")
        con = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute(
            "SELECT player_name, kills, deaths, score FROM scores WHERE server_name = ? ORDER BY score DESC, kills DESC LIMIT 10",
            (server_name,),
        )
        top_players = cur.fetchall()
        con.close()

        embed = discord.Embed(
            title=self.bot._("🏆 PvP Ranking: {server}").format(server=server_name),
            color=discord.Color.gold(),
        )
        if not top_players:
            embed.description = self.bot._("No PvP ranking data available yet.")
        else:
            description = ""
            for i, (player, kills, deaths, score) in enumerate(top_players, 1):
                rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**#{i}**")
                description += self.bot._(
                    "{emoji} **{player}** - Points: {score} (K: {kills} / D: {deaths})\n"
                ).format(
                    emoji=rank_emoji,
                    player=player,
                    score=score,
                    kills=kills,
                    deaths=deaths,
                )
            embed.description = description
        embed.set_footer(
            text=self.bot._("Last update: {date}").format(
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        message_id = self.ranking_state.get(server_name)
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
                return
            except:
                pass

        new_message = await channel.send(embed=embed)
        self.ranking_state[server_name] = new_message.id
        self._save_ranking_state()

    @tasks.loop(minutes=5)
    async def unified_ranking_task(self):
        """Updates unified cluster rankings."""
        unified_configs = getattr(config, "KILLFEED_UNIFIED_RANKINGS", [])
        for u_config in unified_configs:
            if not u_config.get("enabled", True):
                continue
            try:
                await self._update_unified_ranking(u_config)
            except Exception as e:
                logging.error(
                    f"Error updating unified ranking {u_config.get('title')}: {e}"
                )

    async def _update_unified_ranking(self, u_config):
        channel = self.bot.get_channel(u_config["channel_id"])
        if not channel:
            return

        servers = u_config.get("servers_to_include", [])
        if not servers:
            return

        placeholders = ", ".join("?" for _ in servers)
        query = f"""
            SELECT player_name, SUM(kills), SUM(deaths), SUM(score) as total_score 
            FROM scores WHERE server_name IN ({placeholders}) 
            GROUP BY player_name ORDER BY total_score DESC LIMIT 10
        """

        db_path = getattr(config, "KILLFEED_RANKING_DB", "data/killfeed/ranking.db")
        con = sqlite3.connect(f"file:{os.path.abspath(db_path)}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute(query, servers)
        top_players = cur.fetchall()
        con.close()

        embed = discord.Embed(title=u_config["title"], color=discord.Color.purple())
        if not top_players:
            embed.description = self.bot._("No PvP ranking data available yet.")
        else:
            description = ""
            for i, (player, kills, deaths, score) in enumerate(top_players, 1):
                rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**#{i}**")
                description += self.bot._(
                    "{emoji} **{player}** - Points: {score} (K: {kills} / D: {deaths})\n"
                ).format(
                    emoji=rank_emoji,
                    player=player,
                    score=score,
                    kills=kills,
                    deaths=deaths,
                )
            embed.description = description

        embed.set_footer(
            text=self.bot._("Last update: {date}").format(
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        state_id = f"UNIFIED_{u_config['title']}"
        message_id = self.ranking_state.get(state_id)
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
                return
            except:
                pass

        new_message = await channel.send(embed=embed)
        self.ranking_state[state_id] = new_message.id
        self._save_ranking_state()

    @kill_check_task.before_loop
    @ranking_update_task.before_loop
    @unified_ranking_task.before_loop
    async def before_tasks(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(KillfeedCog(bot))
