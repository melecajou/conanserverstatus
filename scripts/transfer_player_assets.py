#!/usr/bin/env python3
"""
Script de Transferência de Construções, Lacaios e Propriedades no game.db (Conan Exiles)

Este script transfere a propriedade de construções, lacaios (thralls/pets),
itens e recipientes de um jogador/clã de origem para um jogador/clã de destino.

Uso:
    python3 scripts/transfer_player_assets.py --source Tharn --dest ADM [--db game.db] [--dry-run]
"""

import argparse
import os
import shutil
import sqlite3
import struct
import sys

def get_entity_info(cursor, name_or_id):
    """
    Localiza o jogador e seu clã pelo nome ou ID.
    Retorna uma tupla (char_id, guild_id, char_name, guild_name).
    """
    # Buscar em personagens
    cursor.execute(
        "SELECT id, char_name, guild FROM characters WHERE char_name = ? OR id = ?",
        (str(name_or_id), str(name_or_id))
    )
    char_row = cursor.fetchone()
    if not char_row:
        return None

    char_id, char_name, guild_id = char_row
    guild_name = None

    if guild_id is not None:
        cursor.execute("SELECT name FROM guilds WHERE guildId = ?", (guild_id,))
        g_row = cursor.fetchone()
        if g_row:
            guild_name = g_row[0]

    return {
        "char_id": char_id,
        "guild_id": guild_id,
        "char_name": char_name,
        "guild_name": guild_name,
        # O proprietário efetivo de construções/itens (se tiver clã, é a guilda; se solo, é o char)
        "effective_owner_id": guild_id if guild_id is not None else char_id
    }

def backup_db(db_path):
    backup_path = f"{db_path}.bak"
    shutil.copyfile(db_path, backup_path)
    print(f"📦 Backup de segurança criado em: {backup_path}")
    return backup_path

def run_transfer(db_path, source_name, dest_name, dry_run=False):
    if not os.path.exists(db_path):
        print(f"❌ Banco de dados não encontrado: {db_path}")
        sys.exit(1)

    print(f"🔍 Analisando banco de dados: {db_path}")
    mode = "ro" if dry_run else "rw"
    conn = sqlite3.connect(f"file:{db_path}?mode={mode}", uri=True)
    cursor = conn.cursor()

    source = get_entity_info(cursor, source_name)
    dest = get_entity_info(cursor, dest_name)

    if not source:
        print(f"❌ Origem '{source_name}' não encontrada na tabela characters.")
        sys.exit(1)
    if not dest:
        print(f"❌ Destino '{dest_name}' não encontrado na tabela characters.")
        sys.exit(1)

    print("\n--- INFORMAÇÕES DE ORIGEM ---")
    print(f"👤 Personagem: {source['char_name']} (ID: {source['char_id']})")
    print(f"🛡️ Clã:        {source['guild_name']} (ID: {source['guild_id']})")
    print(f"🔑 ID Efetivo de Propriedade: {source['effective_owner_id']}")

    print("\n--- INFORMAÇÕES DE DESTINO ---")
    print(f"👤 Personagem: {dest['char_name']} (ID: {dest['char_id']})")
    print(f"🛡️ Clã:        {dest['guild_name']} (ID: {dest['guild_id']})")
    print(f"🔑 ID Efetivo de Propriedade: {dest['effective_owner_id']}")

    source_ids = [source['char_id']]
    if source['guild_id'] is not None:
        source_ids.append(source['guild_id'])

    target_owner_id = dest['effective_owner_id']

    # 1. Contar/Atualizar Construções (buildings)
    placeholders = ",".join("?" * len(source_ids))
    cursor.execute(f"SELECT COUNT(*) FROM buildings WHERE owner_id IN ({placeholders})", source_ids)
    buildings_count = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(bi.instance_id) FROM building_instances bi JOIN buildings b ON bi.object_id = b.object_id WHERE b.owner_id IN ({placeholders})",
        source_ids
    )
    instances_count = cursor.fetchone()[0]

    # 2. Contar/Atualizar Marcadores de Lacaios (follower_markers)
    cursor.execute(f"SELECT COUNT(*) FROM follower_markers WHERE owner_id IN ({placeholders})", source_ids)
    followers_count = cursor.fetchone()[0]

    # 3. Contar/Atualizar Inventários de Itens (item_inventory)
    cursor.execute(f"SELECT COUNT(*) FROM item_inventory WHERE owner_id IN ({placeholders})", source_ids)
    inventory_count = cursor.fetchone()[0]

    # 4. Contar/Atualizar Propriedades de Itens (item_properties)
    cursor.execute(f"SELECT COUNT(*) FROM item_properties WHERE owner_id IN ({placeholders})", source_ids)
    item_props_count = cursor.fetchone()[0]

    # 5. Propriedades com bytes binários (properties)
    bytes_source_char = struct.pack("<I", source['char_id'])
    bytes_source_guild = struct.pack("<I", source['guild_id']) if source['guild_id'] else b""
    bytes_target_owner = struct.pack("<I", target_owner_id)

    query_props = f"""
        SELECT object_id, name, value FROM properties 
        WHERE hex(value) LIKE '%{bytes_source_char.hex()}%'
    """
    if bytes_source_guild:
        query_props += f" OR hex(value) LIKE '%{bytes_source_guild.hex()}%'"

    cursor.execute(query_props)
    matching_props = cursor.fetchall()
    binary_props_count = len(matching_props)

    print("\n--- RESUMO DE ATIVOS A TRANSFERIR ---")
    print(f"🏛️ Estruturas / Bancadas (buildings):     {buildings_count} objetos")
    print(f"🧱 Peças de Construção (building_instances): {instances_count} peças")
    print(f"🐎 Marcadores de Lacaios (follower_markers): {followers_count} lacaios")
    print(f"📦 Inventário Direto (item_inventory):      {inventory_count} linhas")
    print(f"🏷️ Atributos de Itens (item_properties):    {item_props_count} linhas")
    print(f"🔮 Propriedades Binárias (properties):       {binary_props_count} registros")

    if dry_run:
        print("\n⚠️ MODOS DRY-RUN ATIVO: Nenhuma alteração foi gravada no banco.")
        conn.close()
        return

    print("\n🚀 Executando transferência...")
    conn.close()

    # Criar backup antes de modificar em modo rw
    backup_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Update buildings
        cursor.execute(
            f"UPDATE buildings SET owner_id = ? WHERE owner_id IN ({placeholders})",
            [target_owner_id] + source_ids
        )
        up_b = cursor.rowcount

        # Update follower_markers
        cursor.execute(
            f"UPDATE follower_markers SET owner_id = ? WHERE owner_id IN ({placeholders})",
            [target_owner_id] + source_ids
        )
        up_fm = cursor.rowcount

        # Update item_inventory
        cursor.execute(
            f"UPDATE item_inventory SET owner_id = ? WHERE owner_id IN ({placeholders})",
            [target_owner_id] + source_ids
        )
        up_inv = cursor.rowcount

        # Update item_properties
        cursor.execute(
            f"UPDATE item_properties SET owner_id = ? WHERE owner_id IN ({placeholders})",
            [target_owner_id] + source_ids
        )
        up_ip = cursor.rowcount

        # Update binary properties in properties table
        up_bin = 0
        for obj_id, name, val in matching_props:
            new_val = val.replace(bytes_source_char, bytes_target_owner)
            if bytes_source_guild:
                new_val = new_val.replace(bytes_source_guild, bytes_target_owner)
            if new_val != val:
                cursor.execute(
                    "UPDATE properties SET value = ? WHERE object_id = ? AND name = ?",
                    (new_val, obj_id, name)
                )
                up_bin += cursor.rowcount

        conn.commit()
        print("✅ TRANSFERÊNCIA CONCLUÍDA COM SUCESSO!")
        print(f"  • buildings atualizadas:          {up_b}")
        print(f"  • follower_markers atualizados:  {up_fm}")
        print(f"  • item_inventory atualizado:      {up_inv}")
        print(f"  • item_properties atualizadas:    {up_ip}")
        print(f"  • properties binárias atualizadas:{up_bin}")

    except Exception as e:
        conn.rollback()
        print(f"❌ Erro durante a transferência: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transfere construções, lacaios e propriedades no game.db.")
    parser.add_argument("--db", default="game.db", help="Caminho para o arquivo game.db")
    parser.add_argument("--source", default="Tharn", help="Nome ou ID do jogador de origem")
    parser.add_argument("--dest", default="ADM", help="Nome ou ID do jogador de destino")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula a transferência sem alterar o banco")
    parser.add_argument("--apply", action="store_true", help="Aplica as alterações no banco de dados com backup prévio")

    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("ℹ️ Nenhuma opção (--apply ou --dry-run) foi passada. Executando em modo --dry-run por segurança.\n")
        args.dry_run = True

    run_transfer(args.db, args.source, args.dest, dry_run=args.dry_run)
