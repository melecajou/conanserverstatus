import asyncio, os, re, struct, sqlite3
from aiomcrcon import Client
from dotenv import load_dotenv

import config

load_dotenv()

# Pegando dados do primeiro servidor da config como padrão
SERVER_CONF = config.SERVERS[0]
DB_PATH = SERVER_CONF["DB_PATH"]
RCON_IP = SERVER_CONF["SERVER_IP"]
RCON_PORT = SERVER_CONF.get("RCON_PORT", 25575)

CHAR_NAME = "ADM"
CHAR_ID = 201709
SOURCE_SLOT = 0

ID_MAP = {
    "Int": [6, 7, 40, 63, 66, 67, 71, 72, 147],
    "Float": [4, 5, 7, 8, 11, 29, 30]
}

def get_dna(slot):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    res = conn.execute("SELECT template_id, hex(data) FROM item_inventory WHERE owner_id=? AND item_id=? AND inv_type=0", (CHAR_ID, slot)).fetchone()
    conn.close()
    if not res: return None, None
    tid, hex_data = res
    data = bytes.fromhex(hex_data)
    template_hex = struct.pack("<I", tid)
    off = data.find(template_hex)
    if off == -1: return tid, {"int": {}, "float": {}}
    dna = {"int": {}, "float": {}}
    off += 4
    cnt = struct.unpack("<I", data[off:off+4])[0]
    off += 4
    for _ in range(cnt):
        p_id = struct.unpack("<I", data[off:off+4])[0]
        p_val = struct.unpack("<I", data[off+4:off+8])[0]
        if p_id in ID_MAP["Int"]: dna["int"][p_id] = p_val
        off += 8
    if off+4 <= len(data):
        cntf = struct.unpack("<I", data[off:off+4])[0]
        off += 4
        for _ in range(cntf):
            p_id = struct.unpack("<I", data[off:off+4])[0]
            p_val = struct.unpack("<f", data[off+4:off+8])[0]
            if p_id in ID_MAP["Float"]: dna["float"][p_id] = p_val
            off += 8
    return tid, dna

async def master_duplicate():
    client = Client(RCON_IP, RCON_PORT, os.getenv("RCON_PASS"))
    try:
        await client.connect()
        r = await client.send_cmd("ListPlayers")
        idx = None
        for line in r[0].splitlines():
            if CHAR_NAME in line:
                m = re.search(r"^\s*(\d+)\s*\|", line)
                if m: idx = m.group(1); break
        if not idx: return
        tid, dna = get_dna(SOURCE_SLOT)
        print(f"DNA Tid {tid}: {dna}")
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        before = set(conn.execute("SELECT item_id, inv_type FROM item_inventory WHERE owner_id=?", (CHAR_ID,)).fetchall())
        conn.close()
        await client.send_cmd(f"con {idx} SpawnItem {tid} 1")
        await asyncio.sleep(12)
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        after = conn.execute("SELECT item_id, inv_type FROM item_inventory WHERE owner_id=?", (CHAR_ID,)).fetchall()
        conn.close()
        new = next((i for i in after if i not in before), None)
        if new:
            n_slot, i_type = new
            print(f"Injetando em Slot {n_slot} ({i_type})")
            for p_id, v in dna["int"].items(): await client.send_cmd(f"con {idx} SetInventoryItemIntStat {n_slot} {p_id} {v} {i_type}")
            for p_id, v in dna["float"].items(): await client.send_cmd(f"con {idx} SetInventoryItemFloatStat {n_slot} {p_id} {v} {i_type}")
            print("Sucesso.")
        await client.close()
    except Exception as e: print(f"Erro: {e}")

asyncio.run(master_duplicate())