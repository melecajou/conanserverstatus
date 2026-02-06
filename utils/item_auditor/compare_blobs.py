import struct
import sqlite3

DB_PATH = "/home/steam/conan_exiles/ConanSandbox/Saved/game.db"


def get_full_props(slot):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    row = conn.execute(
        "SELECT template_id, hex(data) FROM item_inventory WHERE owner_id = 201709 AND item_id = ? AND inv_type = 0",
        (slot,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    tid, hex_data = row
    data = bytes.fromhex(hex_data)

    template_hex = struct.pack("<I", tid)
    offset = data.find(template_hex)
    if offset == -1:
        return None

    offset += 4
    all_props = {}

    # Ints
    count = struct.unpack("<I", data[offset : offset + 4])[0]
    offset += 4
    for _ in range(count):
        p_id = struct.unpack("<I", data[offset : offset + 4])[0]
        p_val = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        all_props[f"Int_{p_id}"] = p_val
        offset += 8

    # Floats
    if offset + 4 <= len(data):
        count = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        for _ in range(count):
            p_id = struct.unpack("<I", data[offset : offset + 4])[0]
            p_val = struct.unpack("<f", data[offset + 4 : offset + 8])[0]
            all_props[f"Float_{p_id}"] = p_val
            offset += 8
    return all_props


def compare(s1, s2):
    orig = get_full_props(s1)
    dup = get_full_props(s2)
    if not orig or not dup:
        print(f"Erro ao ler slots {s1} ou {s2}")
        return

    print(f"\nComparando Slots {s1} vs {s2}")
    print(f"{'Propriedade':<15} | {'Orig':<15} | {'Dup':<15}")
    print("-" * 50)
    all_keys = sorted(set(orig.keys()) | set(dup.keys()))
    for k in all_keys:
        v_orig = orig.get(k, "MISSING")
        v_dup = dup.get(k, "MISSING")
        mark = "!!!" if v_orig != v_dup else ""
        if mark:
            print(f"{k:<15} | {str(v_orig):<15} | {str(v_dup):<15} {mark}")


print("Análise Soul-Eater:")
compare(26, 31)
print("\nAnálise Espada Curta:")
compare(25, 30)
