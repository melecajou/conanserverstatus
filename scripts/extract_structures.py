import sqlite3
import os
import json

# Caminhos dos bancos de dados
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_EXILE = os.path.join(BASE_DIR, "..", "data", "game.db")
DB_SIPTAH = os.path.join(BASE_DIR, "..", "data", "dlc_siptah.db")
DB_SHEM = os.path.join(BASE_DIR, "..", "data", "shem.db")

# Caminhos de saída
OUTPUT_EXILE = os.path.join(BASE_DIR, "..", "assets", "js", "structures_data.js")
OUTPUT_SIPTAH = os.path.join(BASE_DIR, "..", "assets", "js", "structures_siptah.js")
OUTPUT_SHEM = os.path.join(BASE_DIR, "..", "assets", "js", "structures_shem.js")


def get_structures(db_path):
    if not os.path.exists(db_path):
        print(f"Banco de dados não encontrado: {db_path}")
        return []

    print(f"Lendo banco de dados: {db_path}")
    try:
        # Modo read-only
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Query para pegar estruturas, donos e contar blocos
        query = """
        SELECT 
            b.object_id, 
            ap.x, 
            ap.y, 
            ap.z, 
            COALESCE(g.name, c.char_name, 'Desconhecido') as owner_name,
            COUNT(bi.instance_id) as block_count
        FROM buildings b
        JOIN building_instances bi ON b.object_id = bi.object_id
        JOIN actor_position ap ON b.object_id = ap.id
        LEFT JOIN guilds g ON b.owner_id = g.guildId
        LEFT JOIN characters c ON b.owner_id = c.id
        GROUP BY b.object_id
        """

        cursor.execute(query)
        rows = cursor.fetchall()
        print(f"Query retornou {len(rows)} linhas.")
        if len(rows) > 0:
            print(f"Exemplo de linha: {rows[0]}")

        structures = []
        for row in rows:
            structures.append(
                {
                    "id": row[0],
                    "x": row[1],
                    "y": row[2],
                    "z": row[3],
                    "owner": row[4],
                    "block_count": row[5],
                }
            )

        conn.close()
        return structures
    except Exception as e:
        print(f"Erro ao ler {db_path}: {e}")
        return []


def group_structures(structures, radius=8000):
    grouped = []
    processed = set()

    for i, s1 in enumerate(structures):
        if i in processed:
            continue

        # Novo grupo
        group = {
            "owner": s1["owner"],
            "x": s1["x"],
            "y": s1["y"],
            "z": s1["z"],
            "count": 1,
            "block_count": s1["block_count"],
        }
        processed.add(i)

        # Procura vizinhos do mesmo dono
        for j, s2 in enumerate(structures):
            if j in processed:
                continue

            if s1["owner"] == s2["owner"]:
                dist = ((s1["x"] - s2["x"]) ** 2 + (s1["y"] - s2["y"]) ** 2) ** 0.5
                if dist <= radius:
                    group["block_count"] += s2["block_count"]
                    group["count"] += 1
                    # Recalcula média de posição
                    group["x"] = (group["x"] * (group["count"] - 1) + s2["x"]) / group[
                        "count"
                    ]
                    group["y"] = (group["y"] * (group["count"] - 1) + s2["y"]) / group[
                        "count"
                    ]
                    group["z"] = (group["z"] * (group["count"] - 1) + s2["z"]) / group[
                        "count"
                    ]
                    processed.add(j)

        grouped.append(group)

    return grouped


def save_js(data, filepath, var_name):
    print(f"Salvando {len(data)} bases em {filepath}")
    js_content = f"window.{var_name} = {json.dumps(data, indent=4)};"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(js_content)


def main():
    # Processa Exile
    print("--- Processando Exiled Lands ---")
    structures_exile = get_structures(DB_EXILE)
    grouped_exile = group_structures(structures_exile)
    save_js(grouped_exile, OUTPUT_EXILE, "STRUCTURES_DATA")

    # Processa Siptah
    print("\n--- Processando Isle of Siptah ---")
    structures_siptah = get_structures(DB_SIPTAH)
    grouped_siptah = group_structures(structures_siptah)
    save_js(grouped_siptah, OUTPUT_SIPTAH, "STRUCTURES_SIPTAH")

    # Processa Shem
    print("\n--- Processando Legend of Shem ---")
    structures_shem = get_structures(DB_SHEM)
    grouped_shem = group_structures(structures_shem)
    save_js(grouped_shem, OUTPUT_SHEM, "STRUCTURES_SHEM")


if __name__ == "__main__":
    main()
