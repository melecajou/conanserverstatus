import sys

with open("tests/test_guild_sync_optimization.py", "r") as f:
    content = f.read()

# Fix the assert string issue which we didn't fully replace
content = content.replace("""        # 3. Verify member_active got role added
        # We assume discord.utils.get finds role_a by name
        # Since mock_guild.roles has role_a with correct name

        assert member_active.add_roles.called
        args, _ = member_active.add_roles.call_args
        assert role_a in args

        # 4. Verify member_inactive got role removed
        assert member_inactive.remove_roles.called
        args, _ = member_inactive.remove_roles.call_args
        assert role_b in args""", """        # 3. Verify member_active got role added via edit
        assert member_active.edit.called
        _, kwargs = member_active.edit.call_args
        assert role_a in kwargs.get("roles", [])

        # 4. Verify member_inactive got role removed via edit
        assert member_inactive.edit.called
        _, kwargs = member_inactive.edit.call_args
        assert role_b not in kwargs.get("roles", [])""")

with open("tests/test_guild_sync_optimization.py", "w") as f:
    f.write(content)
