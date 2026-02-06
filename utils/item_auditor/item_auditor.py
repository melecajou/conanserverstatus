import sqlite3
import sys
import struct
import csv


def load_item_names(csv_path="ItemTable.csv"):
    """
    Loads item names from ItemTable.csv and returns a dictionary.
    """
    names = {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) >= 2:
                    try:
                        item_id = int(row[0])
                        # Format: NSLOCTEXT("", "ItemTable_ID_Name", "Real Name")
                        raw_name = row[1]
                        name = raw_name.split('", "')[-1].rstrip('")')

                        # Treatment: unescape characters and remove XX_ prefix
                        name = name.replace("\\'", "'").replace('\\"', '"')
                        if name.startswith("XX_"):
                            name = name[3:]

                        names[item_id] = name
                    except ValueError:
                        continue
    except Exception as e:
        print(f"Warning: Could not load {csv_path}: {e}")
    return names


def format_class_name(class_path):
    """
    Extracts a readable name from a Unreal Engine class path.
    Example: /Game/.../BP_PL_Chest_Large_C -> Chest_Large
    """
    if not class_path:
        return "Unknown"
    return class_path.split(".")[-1].replace("BP_PL_", "").replace("_C", "")


def get_item_report(template_id):
    """
    Queries the database for a specific item ID and generates an aggregated
    report grouped by Clan or individual Player.
    """
    db_path = "game.db"
    item_names = load_item_names()
    item_name = item_names.get(int(template_id), "Unknown Name")

    try:
        # Use read-only mode to prevent locking the database during server operation
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error: Could not connect to database {db_path}: {e}")
        return

    # Comprehensive query to resolve ownership for both player inventories and world containers
    query = """
    SELECT 
        i.inv_type,
        i.data,
        ap.class,
        c.char_name,       
        g_c.name,          
        g_b.name,          
        c_b.char_name,     
        g_cb.name          
    FROM item_inventory i
    -- Join for direct inventory ownership (Players)
    LEFT JOIN characters c ON i.owner_id = c.id 
    LEFT JOIN guilds g_c ON c.guild = g_c.guildId

    -- Join for container ownership (Buildings/Placeables)
    LEFT JOIN buildings b ON i.owner_id = b.object_id AND i.inv_type = 4
    LEFT JOIN actor_position ap ON i.owner_id = ap.id
    
    -- Resolve building owner (either a Guild directly or a Character)
    LEFT JOIN guilds g_b ON b.owner_id = g_b.guildId
    LEFT JOIN characters c_b ON b.owner_id = c_b.id
    LEFT JOIN guilds g_cb ON c_b.guild = g_cb.guildId
    
    WHERE i.template_id = ?
    """

    try:
        cursor.execute(query, (template_id,))
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error executing query: {e}")
        conn.close()
        return

    if not rows:
        print(f"No items found for Template ID: {template_id}")
        conn.close()
        return

    report = {}

    for row in rows:
        (
            inv_type,
            data,
            class_path,
            char_inv,
            guild_inv,
            guild_bldg,
            char_bldg,
            guild_char_bldg,
        ) = row

        # Quantity extraction logic (Robust):
        # We search for the Template ID in the blob to anchor our parsing.
        # The structure is: [TemplateID] [PropCount] [PropID] [Value] ...
        quantity = 1
        if data:
            try:
                # Ensure template_id is treated as int for packing
                tid = int(template_id)
                packed_id = struct.pack("<I", tid)
                offset = data.find(packed_id)

                while offset != -1:
                    cursor = offset + 4
                    if cursor + 4 <= len(data):
                        prop_count = struct.unpack("<I", data[cursor : cursor + 4])[0]
                        cursor += 4

                        if prop_count < 100:  # Sanity check
                            if cursor + (prop_count * 8) <= len(data):
                                for _ in range(prop_count):
                                    prop_id = struct.unpack(
                                        "<I", data[cursor : cursor + 4]
                                    )[0]
                                    cursor += 4
                                    prop_val = struct.unpack(
                                        "<I", data[cursor : cursor + 4]
                                    )[0]
                                    cursor += 4

                                    if prop_id == 1:  # 1 is Quantity
                                        quantity = prop_val
                                break
                    offset = data.find(packed_id, offset + 1)
            except Exception:
                pass

        # Ownership Resolution Strategy:

        # Ownership Resolution Strategy:
        # Prioritizes Clans (Guilds) over individual players.
        # If a player belongs to a clan, the item is attributed to the clan.
        final_owner = (
            guild_bldg
            or guild_char_bldg
            or guild_inv
            or char_bldg
            or char_inv
            or "Unknown"
        )

        if final_owner not in report:
            report[final_owner] = {"Total": 0, "Details": []}

        # Determine the specific location/container
        location_label = ""
        if inv_type == 0:
            player_name = char_inv if char_inv else "Unknown"
            location_label = f"Inventory ({player_name})"
        elif inv_type == 1:
            player_name = char_inv if char_inv else "Unknown"
            location_label = f"Hotbar ({player_name})"
        elif inv_type == 4:
            container_name = format_class_name(class_path)
            location_label = f"Container ({container_name})"
        elif inv_type == 6:
            location_label = "Follower Inventory"
        else:
            location_label = f"Type {inv_type}"

        report[final_owner]["Total"] += quantity
        report[final_owner]["Details"].append((location_label, quantity))

    # Output formatting
    print(f"\nAGGREGATED OWNERSHIP REPORT - ITEM: {item_name} (ID: {template_id})")
    print("-" * 90)
    # Sort groups by total quantity descending
    for owner in sorted(report.keys(), key=lambda x: report[x]["Total"], reverse=True):
        info = report[owner]
        print(f"GROUP: {owner:40} | TOTAL: {info['Total']:>10,}")
        # Sort details alphabetically by location
        for loc, qty in sorted(info["Details"], key=lambda x: x[0]):
            print(f"  └─ {loc:65} : {qty:>10,}")
    print("-" * 90)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 item_auditor.py <template_id>")
    else:
        get_item_report(sys.argv[1])
