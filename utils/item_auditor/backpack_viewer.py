import sqlite3
import struct
import collections
import sys
import csv

def load_item_names(csv_path='ItemTable.csv'):
    """
    Loads item names from ItemTable.csv and returns a dictionary.
    """
    names = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if len(row) >= 2:
                    try:
                        item_id = int(row[0])
                        # Format: NSLOCTEXT("", "ItemTable_ID_Name", "Real Name")
                        raw_name = row[1]
                        if '", "' in raw_name:
                            name = raw_name.split('", "')[-1].rstrip('")')
                        else:
                            name = raw_name
                        
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

def get_backpack_report(target_player=None):
    """
    Scans player inventories (Backpack, Hotbar, Equipment) and lists items.
    """
    db_path = '/home/steam/conan_exiles/ConanSandbox/Saved/game.db'
    item_names = load_item_names()
    try:
        # Use read-only mode to prevent locking the database during server operation
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error: Could not connect to database {db_path}: {e}")
        return

    # inv_type mapping:
    # 0: Backpack
    # 1: Equipment/Armor
    # 2: Hotbar
    query = """
    SELECT 
        c.char_name,
        i.item_id,
        i.template_id,
        i.data,
        i.inv_type
    FROM item_inventory i
    JOIN characters c ON i.owner_id = c.id
    WHERE i.inv_type IN (0, 1, 2)
    """
    
    params = []
    if target_player:
        query += " AND c.char_name LIKE ?"
        params.append(f"%{target_player}%")
    
    query += " ORDER BY c.char_name ASC, i.inv_type ASC, i.item_id ASC"

    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error executing query: {e}")
        conn.close()
        return

    if not rows:
        print(f"No results found for player search.")
        conn.close()
        return

    # Structure: player -> category -> list of items
    player_data = collections.defaultdict(lambda: collections.defaultdict(list))

    for char_name, slot, template_id, data, inv_type in rows:
        quantity = 1
        if data:
            try:
                # Search for the Template ID in the blob
                packed_id = struct.pack('<I', template_id)
                offset = data.find(packed_id)
                
                while offset != -1:
                    cursor_pos = offset + 4
                    if cursor_pos + 4 <= len(data):
                        prop_count = struct.unpack('<I', data[cursor_pos:cursor_pos+4])[0]
                        cursor_pos += 4
                        
                        if prop_count < 100:
                            if cursor_pos + (prop_count * 8) <= len(data):
                                for _ in range(prop_count):
                                    prop_id = struct.unpack('<I', data[cursor_pos:cursor_pos+4])[0]
                                    cursor_pos += 4
                                    prop_val = struct.unpack('<I', data[cursor_pos:cursor_pos+4])[0]
                                    cursor_pos += 4
                                    
                                    if prop_id == 1: # 1 is Quantity
                                        quantity = prop_val
                                break
                    offset = data.find(packed_id, offset + 1)
            except Exception:
                pass

        # Categorize item location
        category = "UNKNOWN"
        if inv_type == 0:
            category = "BACKPACK"
        elif inv_type == 1:
            # Skip internal unarmed hand templates (slots 9 and 10)
            if slot in (9, 10):
                continue
            category = "EQUIPMENT"
        elif inv_type == 2:
            category = "HOTBAR"

        player_data[char_name][category].append({
            "slot": slot,
            "id": template_id,
            "name": item_names.get(template_id, f"Item {template_id}"),
            "qty": quantity
        })

    print(f"\nFULL PLAYER INVENTORY REPORT")
    print("=" * 100)
    
    for player in sorted(player_data.keys()):
        print(f"\nPLAYER: {player}")
        
        # Define print order for categories
        categories = ["EQUIPMENT", "HOTBAR", "BACKPACK"]
        
        for cat in categories:
            items = player_data[player].get(cat, [])
            if items:
                print(f"  --- {cat} ---")
                print(f"  {'SLOT':<10} | {'ITEM NAME':<40} | {'TEMPLATE':<10} | {'QTY':<5}")
                print(f"  {'-'*75}")
                for item in items:
                    print(f"  {item['slot']:<10} | {item['name'][:40]:<40} | {item['id']:<10} | {item['qty']:>5,}")
                print("") # Empty line between categories

        print("-" * 100)

    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print("Usage: python3 backpack_viewer.py [player_name_filter]")
        sys.exit(0)
        
    player_filter = sys.argv[1] if len(sys.argv) > 1 else None
    get_backpack_report(player_filter)
