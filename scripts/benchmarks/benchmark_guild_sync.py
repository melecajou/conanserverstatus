import asyncio
import time
import sys
import os
import unittest.mock
from unittest.mock import MagicMock, AsyncMock

sys.path.append(os.getcwd())

# 1. Mock config
sys.modules["config"] = MagicMock()
import config
config.GUILD_SYNC = {"ENABLED": True, "SERVER_ID": 123, "ROLE_PREFIX": "🛡️ "}
config.SERVERS = [{"DB_PATH": "dummy.db"}]

# 2. Mock discord
mock_discord = MagicMock()
sys.modules["discord"] = mock_discord
sys.modules["discord.ext"] = MagicMock()

# Ensure submodules match sys.modules
mock_commands = MagicMock()
sys.modules["discord.ext.commands"] = mock_commands
sys.modules["discord.ext"].commands = mock_commands

mock_tasks = MagicMock()
sys.modules["discord.ext.tasks"] = mock_tasks
sys.modules["discord.ext"].tasks = mock_tasks

# Mock tasks.loop to return a wrapper
def mock_loop(**kwargs):
    def decorator(func):
        wrapper = MagicMock()
        wrapper.coro = func
        def before_loop(f):
            return f
        wrapper.before_loop = before_loop
        wrapper.start = MagicMock()
        wrapper.cancel = MagicMock()
        return wrapper
    return decorator
sys.modules["discord.ext.tasks"].loop = mock_loop

# Mock commands.Cog
class MockCog:
    def __init_subclass__(cls, **kwargs):
        pass
sys.modules["discord.ext.commands"].Cog = MockCog

# 3. Mock utils.database
mock_utils = MagicMock()
sys.modules["utils"] = mock_utils
mock_db = MagicMock()
sys.modules["utils.database"] = mock_db
mock_utils.database = mock_db
import utils.database

# Mock asyncio.sleep to speed up benchmark
async def mock_sleep(delay):
    pass
asyncio.sleep = mock_sleep

# Now import the Cog
from cogs.guild_sync import GuildSyncCog

# 4. Setup Data for Benchmark
# 10,000 members, 100 active
NUM_MEMBERS = 10000
NUM_ACTIVE = 100
NUM_INACTIVE_WITH_ROLE = 50
NUM_ACTIVE_NEEDS_CHANGE = 50

# Global counters
FETCH_MEMBERS_CALLS = 0
FETCH_MEMBERS_ITERATIONS = 0
GET_MEMBER_CALLS = 0
EDIT_CALLS = 0
ADD_REMOVE_CALLS = 0

# Create Mock Member and Role classes locally for logic
class MockRole:
    def __init__(self, name, members=None):
        self.name = name
        self.members = members or []

class MockMember:
    def __init__(self, id, name, roles=None, bot=False):
        self.id = id
        self.display_name = name
        self.roles = roles or []
        self.bot = bot

    async def add_roles(self, *roles, reason=None):
        global ADD_REMOVE_CALLS
        ADD_REMOVE_CALLS += 1

    async def remove_roles(self, *roles, reason=None):
        global ADD_REMOVE_CALLS
        ADD_REMOVE_CALLS += 1

    async def edit(self, *, roles=None, reason=None):
        global EDIT_CALLS
        EDIT_CALLS += 1

class MockGuild:
    def __init__(self, members, roles):
        self.members_list = members
        self.roles = roles
        self._members_dict = {m.id: m for m in members}

    def get_member(self, user_id):
        global GET_MEMBER_CALLS
        GET_MEMBER_CALLS += 1
        return self._members_dict.get(user_id)

    async def fetch_members(self, limit=None):
        global FETCH_MEMBERS_CALLS, FETCH_MEMBERS_ITERATIONS
        FETCH_MEMBERS_CALLS += 1
        for m in self.members_list:
             FETCH_MEMBERS_ITERATIONS += 1
             yield m

    async def create_role(self, name, **kwargs):
        r = MockRole(name)
        self.roles.append(r)
        return r

async def main():
    print(f"Setting up benchmark with {NUM_MEMBERS} members...")

    prefix = "🛡️ "
    guild_roles = [MockRole(f"{prefix}Guild{i}") for i in range(10)]
    other_roles = [MockRole("Member"), MockRole("Admin")]
    all_roles = guild_roles + other_roles

    members = []
    user_guild_map = {}

    # 1. Active players needing an update (has a role they shouldn't, missing a role they should)
    for i in range(NUM_ACTIVE_NEEDS_CHANGE):
        expected_guild_idx = i % 10
        wrong_guild_idx = (i + 1) % 10
        expected_guild_name = f"Guild{expected_guild_idx}"

        wrong_role = guild_roles[wrong_guild_idx]
        m = MockMember(i, f"PlayerNeedsChange{i}", roles=[wrong_role])
        wrong_role.members.append(m)
        members.append(m)
        user_guild_map[i] = [expected_guild_name]

    # 2. Active players needing NO change
    for i in range(NUM_ACTIVE_NEEDS_CHANGE, NUM_ACTIVE):
        guild_idx = i % 10
        guild_name = f"Guild{guild_idx}"
        role = guild_roles[guild_idx]
        m = MockMember(i, f"PlayerGood{i}", roles=[role])
        role.members.append(m)
        members.append(m)
        user_guild_map[i] = [guild_name]

    # 3. Inactive players with role
    for i in range(NUM_ACTIVE, NUM_ACTIVE + NUM_INACTIVE_WITH_ROLE):
        guild_idx = i % 10
        role = guild_roles[guild_idx]
        m = MockMember(i, f"ExPlayer{i}", roles=[role])
        role.members.append(m)
        members.append(m)

    # 4. Irrelevant members
    for i in range(NUM_ACTIVE + NUM_INACTIVE_WITH_ROLE, NUM_MEMBERS):
        m = MockMember(i, f"Random{i}", roles=[other_roles[0]])
        other_roles[0].members.append(m)
        members.append(m)

    mock_guild = MockGuild(members, all_roles)

    # Setup Bot
    mock_bot = MagicMock()
    mock_bot.get_guild.return_value = mock_guild
    mock_bot._ = MagicMock() # For bot._

    # Instantiate Cog
    cog = GuildSyncCog(mock_bot)

    # Patch utils.database.get_all_guild_members
    utils.database.get_all_guild_members.return_value = user_guild_map

    print("Running sync_guilds_task...")
    start_time = time.time()

    await cog.sync_guilds_task.coro(cog)

    end_time = time.time()
    duration = end_time - start_time

    print(f"Benchmark completed in {duration:.4f}s")
    print(f"get_member calls: {GET_MEMBER_CALLS}")
    print(f"edit() calls: {EDIT_CALLS}")
    print(f"add/remove_roles calls: {ADD_REMOVE_CALLS}")

if __name__ == "__main__":
    asyncio.run(main())
