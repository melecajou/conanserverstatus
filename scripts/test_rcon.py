import asyncio
from aiomcrcon import Client
import config


async def test_rcon_connection():
    """
    Connects to the first server defined in config.py,
    executes 'ListPlayers', and prints the raw output.
    """
    if not hasattr(config, "SERVERS") or not config.SERVERS:
        print("Error: SERVERS not found or empty in config.py.")
        print(
            "Please create a config.py file from config.py.example and fill in your server details."
        )
        return

    server_config = config.SERVERS[0]
    server_name = server_config["NAME"]

    print(f"Attempting to connect to '{server_name}'...")

    client = Client(
        server_config["SERVER_IP"],
        server_config["RCON_PORT"],
        server_config["RCON_PASS"],
    )

    try:
        await client.connect()
        print("Connection successful.")

        print("Executing 'ListPlayers' command...")
        response, _ = await client.send_cmd("ListPlayers")

        print("\n--- Raw Server Response ---")
        print(response)
        print("---------------------------\n")

    except Exception as e:
        print(f"An error occurred: {e}")
        print("Please ensure your config.py file is correct and the server is running.")
    finally:
        await client.close()
        print("Connection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(test_rcon_connection())
    except FileNotFoundError:
        print("Error: config.py not found.")
        print(
            "Please create a config.py file from config.py.example and fill in your server details."
        )
    except Exception as e:
        print(f"A critical error occurred: {e}")
