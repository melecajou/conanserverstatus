import asyncio
import sys
import os

# Adicionar o diretório raiz ao path para importar o config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from cogs.status import StatusCog
from aiomcrcon import Client


async def test_inventory_command(server_name, command_base, target):
    # Procura a config do servidor
    server_conf = next(
        (
            s
            for s in config.SERVERS
            if s["NAME"] == server_name or s.get("ALIAS") == server_name
        ),
        None,
    )
    if not server_conf:
        print(f"Servidor {server_name} não encontrado no config.py")
        return

    client = Client(
        server_conf["SERVER_IP"], server_conf["RCON_PORT"], server_conf["RCON_PASS"]
    )

    try:
        await client.connect()
        # Monta o comando (ex: CheckInventory Tharn ou con 0 CheckInventory Tharn)
        full_command = f"{command_base} {target}"
        print(f"Enviando comando: {full_command}")

        response, _ = await client.send_cmd(full_command)

        print("\n--- RESPOSTA DO SERVIDOR ---")
        print(response)
        print("--- FIM DA RESPOSTA ---\n")

    except Exception as e:
        print(f"Erro ao executar RCON: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 test_inv_rcon.py 'NomeDoServidor' 'ComandoBase' 'Tharn'")
        sys.exit(1)

    asyncio.run(test_inventory_command(sys.argv[1], sys.argv[2], sys.argv[3]))
