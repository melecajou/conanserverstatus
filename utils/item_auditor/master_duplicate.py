import asyncio, os, re, struct, sqlite3, sys
from aiomcrcon import Client
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path para importar o config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import config

load_dotenv()

SERVER_CONF = config.SERVERS[0]
DB_PATH = SERVER_CONF["DB_PATH"]
RCON_IP = SERVER_CONF["SERVER_IP"]
RCON_PORT = SERVER_CONF.get("RCON_PORT", 25575)
CHAR_ID = 201709

# Blacklist de IDs que NÃO devem ser copiados
BLACKLIST = [22] # 22 é o Instance ID único

def get_universal_dna(slot):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    res = conn.execute("SELECT template_id, hex(data) FROM item_inventory WHERE owner_id=? AND item_id=? AND inv_type=0", (CHAR_ID, slot)).fetchone()
    conn.close()
    if not res: return None, None
    
    tid, hex_data = res
    data = bytes.fromhex(hex_data)
    off = data.find(struct.pack("<I", tid)) + 4
    
    dna = {"int": {}, "float": {}}
    
    # Bloco 1: Inteiros
    cnt = struct.unpack("<I", data[off:off+4])[0]
    off += 4
    for _ in range(cnt):
        p_id = struct.unpack("<I", data[off:off+4])[0]
        p_val = struct.unpack("<I", data[off+4:off+8])[0]
        if p_id not in BLACKLIST:
            dna["int"][p_id] = p_val
        off += 8
        
    # Bloco 2: Floats
    if off + 4 <= len(data):
        cntf = struct.unpack("<I", data[off:off+4])[0]
        off += 4
        for _ in range(cntf):
            p_id = struct.unpack("<I", data[off:off+4])[0]
            p_val = struct.unpack("<f", data[off+4:off+8])[0]
            if p_id not in BLACKLIST:
                dna["float"][p_id] = p_val
            off += 8
            
    return tid, dna

async def run():
    client = Client(RCON_IP, RCON_PORT, SERVER_CONF["RCON_PASS"])
    try:
        await client.connect()
        # Vamos testar com o item do Slot 0
        tid, dna = get_universal_dna(0)
        print(f"DNA Universal Extraído (Tid {tid}): {dna}")

        # Capturar estado antes
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        before = set(conn.execute("SELECT item_id, inv_type FROM item_inventory WHERE owner_id=?", (CHAR_ID,)).fetchall())
        conn.close()

        print("Spawnando cópia...")
        await client.send_cmd(f"con 0 SpawnItem {tid} 1")
        await asyncio.sleep(5)

        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        after = conn.execute("SELECT item_id, inv_type FROM item_inventory WHERE owner_id=?", (CHAR_ID,)).fetchall()
        conn.close()
        
        new = next((i for i in after if i not in before), None)
        if new:
            n_slot, i_type = new
            print(f"Injetando DNA Universal no Slot {n_slot}...")
            for p_id, v in dna["int"].items():
                await client.send_cmd(f"con {idx if 'idx' in globals() else 0} SetInventoryItemIntStat {n_slot} {p_id} {v} {i_type}")
            for p_id, v in dna["float"].items():
                await client.send_cmd(f"con {idx if 'idx' in globals() else 0} SetInventoryItemFloatStat {n_slot} {p_id} {v} {i_type}")
            print("Sucesso: Duplicação Universal concluída.")
        await client.close()
    except Exception as e: print(f"Erro: {e}")

asyncio.run(run())