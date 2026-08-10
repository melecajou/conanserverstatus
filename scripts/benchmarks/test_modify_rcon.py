import asyncio
import sys
import os

# Adicionar o diretório raiz ao path para importar o config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from aiomcrcon import Client


async def test_modify_command(server_alias, char_name, slot, new_qty):
    # 1. Achar o servidor
    server_conf = next(
        (
            s
            for s in config.SERVERS
            if s.get("ALIAS") == server_alias or s["NAME"] == server_alias
        ),
        None,
    )
    if not server_conf:
        print(f"Servidor {server_alias} não encontrado.")
        return

    client = Client(
        server_conf["SERVER_IP"], server_conf["RCON_PORT"], server_conf["RCON_PASS"]
    )

    try:
        await client.connect()

        # 2. Achar o IDX do jogador (usando lógica já existente no bot)
        print(f"Buscando IDX para {char_name}...")
        resp_list, _ = await client.send_cmd("ListPlayers")
        idx = None
        for line in resp_list.split("\n"):
            if char_name in line:
                idx = line.split("|")[0].strip()
                break

        if not idx:
            print(f"Jogador {char_name} não encontrado online.")
            return

        # 3. Enviar o comando de modificação
        # con X SetInventoryItemIntStat slot stat value inv_type
        # stat 1 = Quantity, inv_type 0 = Backpack
        cmd = f"con {idx} SetInventoryItemIntStat {slot} 1 {new_qty} 0"
        print(f"Enviando: {cmd}")

        response, _ = await client.send_cmd(cmd)

        print("\n--- RESPOSTA DO SERVIDOR ---")
        print(response)
        print("--- FIM DA RESPOSTA ---\n")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    # Exemplo: python3 test_modify_rcon.py "Siptah" "Tharn" 0 5
    if len(sys.argv) < 5:
        print(
            "Uso: python3 test_modify_rcon.py 'AliasServidor' 'NomeChar' 'Slot' 'NovaQtd'"
        )
        sys.exit(1)

    asyncio.run(test_modify_command(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
