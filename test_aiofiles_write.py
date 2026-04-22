import asyncio
import json
import time
import aiofiles
from scripts.benchmark_status_export import generate_data, prepare_export_data, monitor_loop

async def aiofiles_write(data, path):
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        json_data = json.dumps(data, indent=4, ensure_ascii=False)
        await f.write(json_data)

async def to_thread_write(data, path):
    def write():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    await asyncio.to_thread(write)

async def main():
    cluster_data, server_statuses = generate_data(num_servers=10, players_per_server=2000)
    export_data = prepare_export_data(cluster_data, server_statuses)

    print("--- Benchmarking aiofiles ---")
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_loop(stop_event))
    await asyncio.sleep(0.05)
    start_time = time.perf_counter()
    await aiofiles_write(export_data, "output/aiofiles_status.json")
    end_time = time.perf_counter()
    stop_event.set()
    max_blocking_delay = await monitor_task
    print(f"aiofiles Execution Time: {end_time - start_time:.4f}s")
    print(f"Max Event Loop Blocking Delay: {max_blocking_delay:.4f}s")

    print("\n--- Benchmarking to_thread ---")
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_loop(stop_event))
    await asyncio.sleep(0.05)
    start_time = time.perf_counter()
    await to_thread_write(export_data, "output/tothread_status.json")
    end_time = time.perf_counter()
    stop_event.set()
    max_blocking_delay = await monitor_task
    print(f"to_thread Execution Time: {end_time - start_time:.4f}s")
    print(f"Max Event Loop Blocking Delay: {max_blocking_delay:.4f}s")

if __name__ == "__main__":
    asyncio.run(main())
