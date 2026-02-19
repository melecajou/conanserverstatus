import asyncio
import json
import os
import time
from datetime import datetime

# Ensure output directory exists
os.makedirs("output", exist_ok=True)

# Generate dummy data
def generate_data(num_servers=5, players_per_server=50):
    cluster_data = []
    server_statuses = []

    for i in range(num_servers):
        server_name = f"Server_{i}"
        alias = f"Alias_{i}"

        online_players = []
        for j in range(players_per_server):
            online_players.append({
                "char_name": f"Player_{j}",
                "platform_id": f"ID_{j}"
            })

        cluster_data.append({
            "name": server_name,
            "alias": alias,
            "online_players": online_players,
            "levels_map": {p["char_name"]: 100 for p in online_players},
            "player_data_map": {p["platform_id"]: {"online_minutes": 1000} for p in online_players},
            "system_stats": {"fps": "60", "cpu": "10%", "memory": "2GB"}
        })

        server_statuses.append({
            "alias": alias,
            "online": True,
            "fps": "60"
        })

    return cluster_data, server_statuses

def prepare_export_data(cluster_data, server_statuses):
    export_data = {
        "last_updated": datetime.now().isoformat(),
        "total_players": sum(len(s["online_players"]) for s in cluster_data),
        "servers": [],
    }

    # Create a map for quick lookup of online status
    status_map = {s["alias"]: s["online"] for s in server_statuses}

    # Process each server
    for s in cluster_data:
        online_players = []
        for p in s["online_players"]:
            level = s["levels_map"].get(p["char_name"], 0)
            p_data = s["player_data_map"].get(
                p["platform_id"], {"online_minutes": 0}
            )

            online_players.append(
                {
                    "char_name": p["char_name"],
                    "level": level,
                    "playtime_minutes": p_data["online_minutes"],
                }
            )

        export_data["servers"].append(
            {
                "name": s["name"],
                "alias": s["alias"],
                "online": status_map.get(s["alias"], False),
                "players_count": len(online_players),
                "players": online_players,
                "stats": s["system_stats"],
            }
        )
    return export_data

async def monitor_loop(stop_event):
    """Monitors if the event loop is blocked."""
    max_delay = 0
    last_time = time.perf_counter()
    while not stop_event.is_set():
        await asyncio.sleep(0.01)
        current_time = time.perf_counter()
        delay = current_time - last_time - 0.01
        if delay > max_delay:
            max_delay = delay
        last_time = current_time
    return max_delay

def sync_write(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def async_write(data, path):
    def write():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    await asyncio.to_thread(write)

async def run_benchmark():
    cluster_data, server_statuses = generate_data(num_servers=10, players_per_server=2000) # Large data to notice blocking
    export_data = prepare_export_data(cluster_data, server_statuses)

    print(f"Data size: {len(json.dumps(export_data))} bytes")

    # Benchmark Sync
    print("\n--- Benchmarking Synchronous Write ---")
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_loop(stop_event))
    await asyncio.sleep(0.05) # Give monitor loop a chance to start

    start_time = time.perf_counter()
    sync_write(export_data, "output/status_sync.json")
    end_time = time.perf_counter()

    stop_event.set()
    max_blocking_delay = await monitor_task
    print(f"Sync Execution Time: {end_time - start_time:.4f}s")
    print(f"Max Event Loop Blocking Delay: {max_blocking_delay:.4f}s")

    # Benchmark Async
    print("\n--- Benchmarking Asynchronous Write ---")
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_loop(stop_event))
    await asyncio.sleep(0.05) # Give monitor loop a chance to start

    start_time = time.perf_counter()
    await async_write(export_data, "output/status_async.json")
    end_time = time.perf_counter()

    stop_event.set()
    max_blocking_delay = await monitor_task
    print(f"Async Execution Time: {end_time - start_time:.4f}s")
    print(f"Max Event Loop Blocking Delay: {max_blocking_delay:.4f}s")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
