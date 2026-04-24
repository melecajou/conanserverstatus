import asyncio
import time

class MockLogWatcher:
    async def read_new_lines(self):
        await asyncio.sleep(0.1)  # Simulate I/O latency
        return ["log1", "log2"]

class MockMarketplaceCog:
    def __init__(self):
        self.watchers = {
            "Server1": MockLogWatcher(),
            "Server2": MockLogWatcher(),
            "Server3": MockLogWatcher(),
            "Server4": MockLogWatcher(),
        }

    async def _process_log_for_server(self, server_conf):
        server_name = server_conf["NAME"]
        await self.watchers[server_name].read_new_lines()
        # Simulate processing time
        await asyncio.sleep(0.05)

async def test_sequential(cog, servers):
    start = time.time()
    for server_conf in servers:
        await cog._process_log_for_server(server_conf)
    end = time.time()
    return end - start

async def test_parallel(cog, servers):
    start = time.time()
    async def safe_process(server_conf):
        try:
            await cog._process_log_for_server(server_conf)
        except Exception:
            pass

    tasks = [safe_process(server_conf) for server_conf in servers]
    if tasks:
        await asyncio.gather(*tasks)
    end = time.time()
    return end - start

async def main():
    cog = MockMarketplaceCog()
    servers = [{"NAME": f"Server{i}"} for i in range(1, 5)]

    print("Benchmarking Server Config Loop Optimization")
    print("-" * 50)

    seq_time = await test_sequential(cog, servers)
    print(f"Sequential (Baseline): {seq_time:.4f} seconds")

    par_time = await test_parallel(cog, servers)
    print(f"Parallel (Optimized):   {par_time:.4f} seconds")
    print(f"Speedup:                {seq_time / par_time:.2f}x")

if __name__ == "__main__":
    asyncio.run(main())
