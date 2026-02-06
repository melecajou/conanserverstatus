import sqlite3
import sys
import struct
import collections
import csv


def load_item_names(csv_path="ItemTable.csv"):
    names = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    try:
                        item_id = int(row[0])
                        raw_name = row[1]
                        if '", "' in raw_name:
                            name = raw_name.split('", "')[-1].rstrip('")')
                        else:
                            name = raw_name
                        name = name.replace("'", "'").replace('"', '"')
                        if name.startswith("XX_"):
                            name = name[3:]
                        names[item_id] = name
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Warning: Could not load {csv_path}: {e}")
    return names


def format_class_name(class_path):
    if not class_path:
        return "Unknown"
    return class_path.split(".")[-1].replace("BP_PL_", "").replace("_C", "")


def get_clan_audit(clan_name_filter):
    db_path = "game.db"
    item_names = load_item_names()

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error: Could not connect to database {db_path}: {e}")
        return

    # 1. Find the Guild(s) matching the name
    cursor.execute(
        "SELECT guildId, name FROM guilds WHERE name LIKE ?", (f"%{clan_name_filter}%",)
    )
    guilds = cursor.fetchall()

    if not guilds:
        print(f"No clans found matching: {clan_name_filter}")
        conn.close()
        return

    for guild_id, real_clan_name in guilds:
        print(f"\nAUDITING CLAN: {real_clan_name} (ID: {guild_id})")
        print("=" * 100)

        # Query for all items owned by the clan (buildings) or its members (inventories)
        query = """
        SELECT 
            i.template_id,
            i.data,
            i.inv_type,
            ap.class,
            c.char_name
        FROM item_inventory i
        LEFT JOIN characters c ON i.owner_id = c.id
        LEFT JOIN buildings b ON i.owner_id = b.object_id AND i.inv_type = 4
        LEFT JOIN actor_position ap ON i.owner_id = ap.id
        WHERE 
            (c.guild = ?) OR
            (b.owner_id = ?) OR
            (b.owner_id IN (SELECT id FROM characters WHERE guild = ?))
        """

        cursor.execute(query, (guild_id, guild_id, guild_id))
        rows = cursor.fetchall()

        if not rows:
            print("No items found for this clan.")
            continue

        inventory_summary = collections.defaultdict(int)

        for template_id, data, inv_type, class_path, char_name in rows:
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
                                        if prop_id == 1:
                                            quantity = prop_val
                                    break
                        offset = data.find(packed_id, offset + 1)
                except:
                    pass

            inventory_summary[template_id] += quantity

        # Output the summary sorted by quantity descending
        print(f"{'ITEM ID':<10} | {'ITEM NAME':<50} | {'TOTAL QTY':>15}")
        print("-" * 100)

        sorted_items = sorted(
            inventory_summary.items(), key=lambda x: x[1], reverse=True
        )
        for tid, qty in sorted_items:
            name = item_names.get(tid, f"Unknown ({tid})")
            print(f"{tid:<10} | {name[:50]:<50} | {qty:>15,}")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 clan_auditor.py <clan_name>")
    else:
        get_clan_audit(sys.argv[1])
