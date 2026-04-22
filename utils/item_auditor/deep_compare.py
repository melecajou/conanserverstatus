import struct
import sqlite3
import os
import argparse

DEFAULT_DB_PATH = "/home/steam/conan_exiles/ConanSandbox/Saved/game.db"


def deep_parse_blob(slot, db_path=None):
    if db_path is None:
        db_path = os.getenv("GAME_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    row = conn.execute(
        "SELECT template_id, hex(data) FROM item_inventory WHERE owner_id = 201709 AND item_id = ? AND inv_type = 0",
        (slot,),
    ).fetchone()
    conn.close()
    if not row:
        return None, None
    tid, hex_data = row
    data = bytes.fromhex(hex_data)
    template_hex = struct.pack("<I", tid)
    offset = data.find(template_hex)
    if offset == -1:
        return tid, {}
    results = {"raw_hex": hex_data, "props": []}
    offset += 4
    if offset + 4 <= len(data):
        count = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        for _ in range(count):
            if offset + 8 <= len(data):
                p_id = struct.unpack("<I", data[offset : offset + 4])[0]
                p_val = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
                results["props"].append(("Int", p_id, p_val))
                offset += 8
    if offset + 4 <= len(data):
        count = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        for _ in range(count):
            if offset + 8 <= len(data):
                p_id = struct.unpack("<I", data[offset : offset + 4])[0]
                p_hex = data[offset + 4 : offset + 8]
                p_float = struct.unpack("<f", p_hex)[0]
                results["props"].append(("Float", p_id, p_float))
                offset += 8
    if offset < len(data):
        results["trailing"] = data[offset:].hex()
    return tid, results


def run_comparison(slot1, slot2, db_path=None):
    tid, r1 = deep_parse_blob(slot1, db_path)
    _, r2 = deep_parse_blob(slot2, db_path)

    if not r1 or not r2:
        print(f"Erro ao ler slots {slot1} ou {slot2}")
        return

    print("--- COMPARACAO COMPLETA ---")
    p1 = {(t, i): v for t, i, v in r1["props"]}
    p2 = {(t, i): v for t, i, v in r2["props"]}
    keys = sorted(set(p1.keys()) | set(p2.keys()))
    for k in keys:
        v1 = p1.get(k, "FALTA")
        v2 = p2.get(k, "FALTA")
        m = "!!!" if v1 != v2 else ""
        print(f"{k[0]} {k[1]:<3} | {v1} | {v2} {m}")
    if "trailing" in r1 or "trailing" in r2:
        print("Trailing 1:", r1.get("trailing", "N/A"))
        print("Trailing 2:", r2.get("trailing", "N/A"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep compare item properties between two slots.")
    parser.add_argument("slot1", type=int, nargs="?", default=25, help="First slot to compare.")
    parser.add_argument("slot2", type=int, nargs="?", default=30, help="Second slot to compare.")
    parser.add_argument(
        "--db",
        help="Path to the game.db file.",
        default=os.getenv("GAME_DB_PATH", DEFAULT_DB_PATH),
    )
    args = parser.parse_args()
    run_comparison(args.slot1, args.slot2, args.db)
