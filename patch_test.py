import sys

with open("tests/test_guild_sync_optimization.py", "r") as f:
    content = f.read()

# Fix the assert string issue which we didn't fully replace
# The previous version used spaces incorrectly for what was actually in the file
search_string = """            # 3. Verify member_active got role added
            # We assume discord.utils.get finds role_a by name
            # Since mock_guild.roles has role_a with correct name

        # 3. Verify member_active got role added via edit
        assert member_active.edit.called
        _, kwargs = member_active.edit.call_args
        assert role_a in kwargs.get('roles', [])

        # 4. Verify member_inactive got role removed via edit
        assert member_inactive.edit.called
        _, kwargs = member_inactive.edit.call_args
        assert role_b not in kwargs.get('roles', [])"""

replace_string = """            # 3. Verify member_active got role added via edit
            assert member_active.edit.called
            _, kwargs = member_active.edit.call_args
            assert role_a in kwargs.get('roles', [])

            # 4. Verify member_inactive got role removed via edit
            assert member_inactive.edit.called
            _, kwargs = member_inactive.edit.call_args
            assert role_b not in kwargs.get('roles', [])"""

if search_string in content:
    content = content.replace(search_string, replace_string)
    with open("tests/test_guild_sync_optimization.py", "w") as f:
        f.write(content)
    print("Replacement successful")
else:
    # If exact match fails, let's try to be more robust or diagnose
    print("Search string not found")
    # For diagnosis:
    if "Since mock_guild.roles has role_a with correct name" in content:
        print("Found the partial string, but full block didn't match.")
