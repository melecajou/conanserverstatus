
import asyncio
from aiomcrcon import Client, RCONConnectionError
import config

async def diagnose_rcon_connection():
    """
    Performs a single, isolated connection and command test to diagnose
    RCON authentication issues.
    """
    try:
        # Use the first server from the config (Ecos da Hyboria - Exílio)
        server_config = config.SERVERS[0]
        server_name = server_config["NAME"]
        host = server_config["SERVER_IP"]
        port = server_config["RCON_PORT"]
        password = server_config["RCON_PASS"]
    except (IndexError, KeyError) as e:
        print(f"Configuration error in config.py: {e}")
        return

    print(f"--- RCON Diagnostic Test for: {server_name} ---")
    print(f"Attempting to connect to {host}:{port}...")

    client = None
    try:
        client = Client(host, port, password)
        await client.connect()
        print("[SUCCESS] Connection established.")

        print("\nAttempting to send 'ListPlayers' command...")
        response, _unused = await client.send_cmd("ListPlayers")
        print("[SUCCESS] Command sent successfully.")
        print("\n--- Server Response ---")
        print(response)
        print("-----------------------\n")
        print("Diagnostic complete. The credentials and connection appear to be valid.")

    except RCONConnectionError as e:
        print(f"\n[FAILURE] A critical RCON connection error occurred: {e}")
        print("This indicates a problem with the password, network, or server RCON port.")
    except Exception as e:
        print(f"\n[FAILURE] An unexpected error occurred: {e}")
    finally:
        if client:
            await client.close()
            print("\nConnection closed.")

if __name__ == "__main__":
    asyncio.run(diagnose_rcon_connection())
