from discord.ext import commands, tasks
import discord
import logging
import sqlite3
import os
import shutil

import config
from utils.database import get_global_player_data


def get_platform_id_for_player(player_id, game_db_path):
    """Gets the platform ID for a given player ID from the game DB."""
    if not player_id or not os.path.exists(game_db_path):
        return None
    try:
        with sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()
            cur.execute("SELECT platformId FROM account WHERE id = ?", (player_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception as e:
        logging.error(f"Failed to get platform ID for player {player_id}: {e}")
        return None


def get_vip_level_for_player(platform_id):
    """Gets the VIP level for a given platform ID from the global registry."""
    if not platform_id:
        return 0
    try:
        data = get_global_player_data([platform_id])
        if platform_id in data:
            return data[platform_id]["vip_level"]
    except Exception as e:
        logging.error(f"Failed to get VIP level for platform {platform_id}: {e}")
    return 0


def get_owner_details(owner_id, game_db_path, player_db_path):
    """Gets owner details (name, vip_level, type) from the game and player DBs."""
    # Wrapper for backward compatibility or single use cases, implemented via batch
    result = get_batch_owner_details([owner_id], game_db_path, player_db_path)
    return result.get(owner_id, (None, 0, "unknown"))


def get_batch_owner_details(owner_ids, game_db_path, player_db_path):
    """
    Gets owner details (name, vip_level, type) for a batch of owner_ids.
    Returns a dictionary: {owner_id: (name, vip_level, type)}
    """
    results = {oid: (None, 0, "unknown") for oid in owner_ids}
    if not owner_ids or not os.path.exists(game_db_path):
        return results

    try:
        with sqlite3.connect(f"file:{game_db_path}?mode=ro", uri=True) as con:
            cur = con.cursor()

            # 1. Identify Guilds
            guild_owners = {} # guild_id -> name
            # Chunking 900
            for i in range(0, len(owner_ids), 900):
                batch = owner_ids[i:i+900]
                placeholders = ",".join("?" * len(batch))
                cur.execute(f"SELECT guildId, name FROM guilds WHERE guildId IN ({placeholders})", batch)
                for gid, name in cur.fetchall():
                    guild_owners[gid] = name

            # 2. Identify Players (from owner_ids that are not guilds)
            potential_player_ids = [oid for oid in owner_ids if oid not in guild_owners]
            player_owners = {} # char_id -> (name, player_id)

            if potential_player_ids:
                for i in range(0, len(potential_player_ids), 900):
                    batch = potential_player_ids[i:i+900]
                    placeholders = ",".join("?" * len(batch))
                    cur.execute(f"SELECT id, char_name, playerId FROM characters WHERE id IN ({placeholders})", batch)
                    for char_id, name, pid in cur.fetchall():
                        player_owners[char_id] = (name, pid)

            # 3. Get Members for Guilds
            guild_members = {} # guild_id -> list of player_ids
            if guild_owners:
                guild_ids = list(guild_owners.keys())
                for i in range(0, len(guild_ids), 900):
                    batch = guild_ids[i:i+900]
                    placeholders = ",".join("?" * len(batch))
                    cur.execute(f"SELECT guild, playerId FROM characters WHERE guild IN ({placeholders})", batch)
                    for gid, pid in cur.fetchall():
                        if gid not in guild_members:
                            guild_members[gid] = []
                        guild_members[gid].append(pid)

            # 4. Collect all player IDs to fetch Platform IDs
            all_player_ids = set()
            for _, pid in player_owners.values():
                all_player_ids.add(pid)
            for pids in guild_members.values():
                all_player_ids.update(pids)

            # 5. Fetch Platform IDs
            player_platform_map = {} # player_id -> platform_id
            all_player_ids_list = list(all_player_ids)
            if all_player_ids_list:
                for i in range(0, len(all_player_ids_list), 900):
                    batch = all_player_ids_list[i:i+900]
                    placeholders = ",".join("?" * len(batch))
                    cur.execute(f"SELECT id, platformId FROM account WHERE id IN ({placeholders})", batch)
                    for pid, platform_id in cur.fetchall():
                        player_platform_map[pid] = platform_id

            # 6. Fetch VIP Levels
            all_platform_ids = list(set(player_platform_map.values()))
            platform_vip_map = {} # platform_id -> vip_level

            if all_platform_ids:
                # Chunking calls to get_global_player_data just in case
                for i in range(0, len(all_platform_ids), 900):
                    batch = all_platform_ids[i:i+900]
                    data = get_global_player_data(batch)
                    for platform_id, info in data.items():
                        platform_vip_map[platform_id] = info.get("vip_level", 0)

            # 7. Resolve Results

            # For Guilds
            for gid, gname in guild_owners.items():
                max_vip = 0
                members = guild_members.get(gid, [])
                for pid in members:
                    platform_id = player_platform_map.get(pid)
                    if platform_id:
                        vip = platform_vip_map.get(platform_id, 0)
                        if vip > max_vip:
                            max_vip = vip
                results[gid] = (gname, max_vip, "guild")

            # For Players
            for char_id, (cname, pid) in player_owners.items():
                platform_id = player_platform_map.get(pid)
                vip = 0
                if platform_id:
                    vip = platform_vip_map.get(platform_id, 0)
                results[char_id] = (cname, vip, "player")

    except Exception as e:
        logging.error(f"Failed to get batch owner details: {e}")

    return results


class BuildingCog(commands.Cog, name="Building"):
    """Handles the hourly building reports."""

    def __init__(self, bot):
        self.bot = bot
        self.building_report_messages = {}
        self.update_building_report_task.start()

    def cog_unload(self):
        self.update_building_report_task.cancel()

    @tasks.loop(hours=1)
    async def update_building_report_task(self):
        for server_conf in config.SERVERS:
            watcher_config = server_conf.get("BUILDING_WATCHER")
            if not watcher_config or not watcher_config.get("ENABLED"):
                continue

            channel_id = watcher_config.get("CHANNEL_ID")
            sql_path = watcher_config.get("SQL_PATH")
            db_backup_path = watcher_config.get("DB_BACKUP_PATH")
            default_build_limit = watcher_config.get("BUILD_LIMIT", 99999)
            game_db_path = server_conf.get("DB_PATH")
            player_db_path = server_conf.get("PLAYER_DB_PATH")

            if not all(
                [channel_id, sql_path, db_backup_path, game_db_path, player_db_path]
            ):
                logging.error(
                    self.bot._(
                        "Building Watcher for '{server_name}' is missing required configuration."
                    ).format(server_name=server_conf["NAME"])
                )
                continue

            logging.info(f"Starting building watcher for server: {server_conf['NAME']}")
            results = []
            try:
                with open(sql_path, "r") as f:
                    sql_script = f.read()
                with sqlite3.connect(f"file:{db_backup_path}?mode=ro", uri=True) as con:
                    cur = con.cursor()
                    cur.execute(sql_script)
                    results = cur.fetchall()
                logging.info(
                    f"Building watcher query successful for {server_conf['NAME']}. Found {len(results)} owners."
                )
            except Exception as e:
                logging.error(
                    self.bot._(
                        "Failed to generate building report for '{server_name}'. Exception: {error}"
                    ).format(server_name=server_conf["NAME"], error=e),
                    exc_info=True,
                )
                continue

            embed = discord.Embed(
                title=self.bot._("Building Report - {server_name}").format(
                    server_name=server_conf["NAME"]
                ),
                color=discord.Color.blue(),
            )

            if not results:
                embed.description = self.bot._("No buildings found at the moment.")
            else:
                description_lines = []

                # BATCH OPTIMIZATION START
                owner_ids = [r[0] for r in results]
                owner_details_map = get_batch_owner_details(
                    owner_ids, game_db_path, player_db_path
                )
                # BATCH OPTIMIZATION END

                for i, (owner_id, pieces) in enumerate(results, 1):
                    # Use the batch fetched details
                    owner_name, vip_level, owner_type = owner_details_map.get(
                        owner_id, (None, 0, "unknown")
                    )

                    if not owner_name:
                        owner_name = self.bot._("(Unknown Owner)")

                    build_limit = default_build_limit
                    if vip_level == 1:
                        build_limit = 3500
                    elif vip_level == 2:
                        build_limit = 4000

                    line = f"**{i}.** {owner_name}: `{pieces}` peças (Premium: {vip_level}, Limite: {build_limit})"

                    if pieces > build_limit:
                        line += self.bot._(" ⚠️ (Acima do limite)").format(
                            build_limit=build_limit
                        )
                    description_lines.append(line)

                full_description = "\n".join(description_lines)
                if len(full_description) > 4096:
                    full_description = full_description[:4090] + "\n..."
                embed.description = full_description

            embed.set_footer(text=self.bot._("Updated"))
            embed.timestamp = discord.utils.utcnow()

            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logging.error(
                        self.bot._(
                            "Building report channel {channel_id} not found."
                        ).format(channel_id=channel_id)
                    )
                    continue

                report_message = self.building_report_messages.get(channel_id)
                if report_message:
                    await report_message.edit(embed=embed)
                else:
                    async for msg in channel.history(limit=50):
                        if (
                            msg.author.id == self.bot.user.id
                            and msg.embeds
                            and msg.embeds[0].title.startswith(
                                self.bot._("Building Report")
                            )
                        ):
                            self.building_report_messages[channel_id] = msg
                            await msg.edit(embed=embed)
                            break
                    else:
                        new_msg = await channel.send(embed=embed)
                        self.building_report_messages[channel_id] = new_msg
            except Exception as e:
                logging.error(
                    self.bot._(
                        "Failed to post building report for '{server_name}': {error}"
                    ).format(server_name=server_conf["NAME"], error=e)
                )

    @update_building_report_task.before_loop
    async def before_building_report_task(self):
        await self.bot.wait_until_ready()
        # Call the task once immediately
        await self.update_building_report_task.coro(self)


async def setup(bot):
    await bot.add_cog(BuildingCog(bot))
