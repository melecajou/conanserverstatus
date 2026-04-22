import sys

with open("scripts/benchmark_guild_sync_edit.py", "r") as f:
    content = f.read()

content = content.replace("""    async def edit(self, *, roles=None, reason=None):
        global API_CALLS
        API_CALLS += 1""", "")

with open("scripts/benchmark_guild_sync_edit.py", "w") as f:
    f.write(content)
