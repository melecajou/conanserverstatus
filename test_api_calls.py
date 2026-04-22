import sys

with open("scripts/benchmark_guild_sync.py", "r") as f:
    content = f.read()

content = content.replace("""    async def add_roles(self, *roles, reason=None):
        global API_CALLS
        API_CALLS += 1""", """    async def add_roles(self, *roles, reason=None):
        global API_CALLS
        API_CALLS += 1
        print(f"add_roles called for {self.display_name} with {[r.name for r in roles]}")""")

content = content.replace("""    async def remove_roles(self, *roles, reason=None):
        global API_CALLS
        API_CALLS += 1""", """    async def remove_roles(self, *roles, reason=None):
        global API_CALLS
        API_CALLS += 1
        print(f"remove_roles called for {self.display_name} with {[r.name for r in roles]}")""")

with open("scripts/benchmark_guild_sync_debug.py", "w") as f:
    f.write(content)
