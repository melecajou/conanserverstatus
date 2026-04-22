import sys

with open("tests/test_guild_sync_optimization.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if "assert member_active.add_roles.called" in line:
        skip = True
        new_lines.append("        # 3. Verify member_active got role added via edit\n")
        new_lines.append("        assert member_active.edit.called\n")
        new_lines.append("        _, kwargs = member_active.edit.call_args\n")
        new_lines.append("        assert role_a in kwargs.get('roles', [])\n\n")
        new_lines.append("        # 4. Verify member_inactive got role removed via edit\n")
        new_lines.append("        assert member_inactive.edit.called\n")
        new_lines.append("        _, kwargs = member_inactive.edit.call_args\n")
        new_lines.append("        assert role_b not in kwargs.get('roles', [])\n")
    elif "assert role_b in args" in line:
        skip = False
    elif not skip:
        new_lines.append(line)

with open("tests/test_guild_sync_optimization.py", "w") as f:
    f.writelines(new_lines)
