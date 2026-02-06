import sqlite3
import sys
import struct


def format_class_name(class_path):
    if not class_path:
        return "Desconhecido"
    return class_path.split(".")[-1].replace("BP_PL_", "").replace("_C", "")


def get_item_report(template_id):
    try:
        conn = sqlite3.connect("game.db")
        cursor = conn.cursor()
    except Exception as e:
        print(f"Erro ao abrir o banco de dados: {e}")
        return

    # Nova Query: Busca guildas vinculadas aos personagens
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
    -- 1. Join para Dono do Inventário
    LEFT JOIN characters c ON i.owner_id = c.id 
    LEFT JOIN guilds g_c ON c.guild = g_c.guildId

    -- 2. Join para Dono do Baú/Bancada
    LEFT JOIN buildings b ON i.owner_id = b.object_id AND i.inv_type = 4
    LEFT JOIN actor_position ap ON i.owner_id = ap.id
    
    -- 2.1 Quem é o dono do prédio? (Guilda Direta, ou Personagem e sua Guilda)
    LEFT JOIN guilds g_b ON b.owner_id = g_b.guildId
    LEFT JOIN characters c_b ON b.owner_id = c_b.id
    LEFT JOIN guilds g_cb ON c_b.guild = g_cb.guildId
    
    WHERE i.template_id = ?
    """

    cursor.execute(query, (template_id,))
    rows = cursor.fetchall()

    if not rows:
        print(f"Nenhum item com ID {template_id} encontrado.")
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

        # Lógica de Quantidade (Mantida da versão anterior corrigida)
        quantidade = 1
        if data:
            pattern_qty = b"\x03\x00\x00\x00\x01\x00\x00\x00"
            idx = data.find(pattern_qty)
            if idx != -1:
                start_qty = idx + len(pattern_qty)
                if len(data) >= start_qty + 4:
                    val = struct.unpack("<I", data[start_qty : start_qty + 4])[0]
                    if val < 1000000000:  # Filtro de sanidade leve
                        quantidade = val

        # Lógica de Dono "Definitivo" (Prioridade para Guilda)
        # Ordem: Guilda do Prédio > Guilda do Dono do Prédio > Guilda do Inventário > Nome do Dono Prédio > Nome Dono Inv
        dono_final = (
            guild_bldg
            or guild_char_bldg
            or guild_inv
            or char_bldg
            or char_inv
            or "Desconhecido"
        )

        if dono_final not in report:
            report[dono_final] = {"Total": 0, "Detalhes": []}

        # Formatação do Local para saber quem está segurando
        tipo_local = ""
        if inv_type == 0:
            # Se agrupou por guilda, mostra de quem é o inventário
            quem = char_inv if char_inv else "Desconhecido"
            tipo_local = f"Inventário ({quem})"
        elif inv_type == 1:
            quem = char_inv if char_inv else "Desconhecido"
            tipo_local = f"Hotbar ({quem})"
        elif inv_type == 4:
            nome_recipiente = format_class_name(class_path)
            tipo_local = f"Recipiente ({nome_recipiente})"
        elif inv_type == 6:
            tipo_local = "Inventário de Seguidor"
        else:
            tipo_local = f"Tipo {inv_type}"

        report[dono_final]["Total"] += quantidade
        report[dono_final]["Detalhes"].append((tipo_local, quantidade))

    print(f"\nRelatório Agrupado por CLÃ/JOGADOR - Item ID: {template_id}")
    print("-" * 85)
    for dono in sorted(report.keys(), key=lambda x: report[x]["Total"], reverse=True):
        info = report[dono]
        print(f"GRUPO: {dono:35} | TOTAL: {info['Total']:>10,}")
        # Ordenar detalhes para inventários ficarem juntos
        for local, qtd in sorted(info["Detalhes"], key=lambda x: x[0]):
            print(f"  └─ {local:60} : {qtd:>10,}")
    print("-" * 85)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 consultar_item.py <item_id>")
    else:
        get_item_report(sys.argv[1])
