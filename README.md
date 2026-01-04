# Conan Exiles Server Status Bot

This Discord bot monitors the status of one or more Conan Exiles servers. It is designed to be highly configurable, providing real-time updates on server status, online players, and other automated reports directly to your Discord channels.

## Features

- **Multi-Server Monitoring**: Tracks multiple servers simultaneously, each with its own configuration.
- **Consolidated Cluster Status**: Optionally consolidates the status of all servers into a single channel, providing a unified view of online players and aggregated system statistics.
- **Efficient Live Status**: Displays an auto-updating list of online players, including their in-game level and total playtime. This process is highly optimized, using asynchronous, non-blocking database queries to ensure minimal performance impact.
- **Robust Playtime Rewards**: A per-server reward system with tiered VIP levels. VIP status is now **centralized globally** by Discord account, meaning a VIP player enjoys benefits across all servers in your cluster.
- **Global Player Registration**: A streamlined process for players to link their in-game character to their Discord account using a `/register` command. Once registered on any server, the player is automatically recognized on **all other servers** in the cluster without needing to register again.
- **Automated Role Assignment**: Automatically assigns a specific Discord role to users upon successful registration. Includes a sync command to retroactively apply roles to already registered users.
- **Admin Commands**: Provides administrative functionalities:
    - `/setvip @User <level> [days]`: Sets the user's VIP level **globally**. Optionally, set the number of days for reward benefits (permanent if omitted).
    - `/listvips`: Lists all players with an active VIP level and their expiration status.
    - `/checkvip @User`: Checks the VIP status, level, and expiration of a specific member.
    - `/setvipexpiry @User <days>`: Updates the expiration duration for an existing VIP member.
    - `/sync_roles`: Iterates through all player databases and assigns the configured registered role to any user who has linked their account but doesn't have the role yet.
- **User Commands**:
    - `/register`: Generates a code to link your in-game character to your Discord account.
    - `/premium`: Checks your own current VIP status, level, and benefit expiration date.
    - `/finduser <char_name>`: Finds the Discord user linked to a specific in-game character name.
- **Warp System**: Allows registered players to teleport to pre-defined locations using the in-game command `!warp <location>`.
    - **Cooldowns**: Configurable cooldown period to prevent abuse.
    - **Feedback**: Sends a Direct Message to the user upon successful teleportation.
    - **Restrictions**: Only players with a linked Discord account can use this feature.
    - **List Warps**: Use `/warps` in Discord or `!warps` in the in-game chat to see a list of available locations.
- **Home System**: Allows players to set a personal teleport point.
    - `!sethome`: Saves the player's current position as their home.
    - `!home`: Teleports the player back to their saved home position.
    - **Note**: The position is read from the game database. There might be a slight delay in coordinate accuracy (up to 1 minute) depending on the server's automatic save cycle.
    - **Cooldowns**: Both `!sethome` and `!home` have configurable cooldowns.
- **Guild Sync**: Automatically synchronizes in-game guild membership with Discord roles.
    - Creates roles like `🛡️ GuildName` automatically.
    - Assigns roles to registered members.
    - Removes roles when a player leaves a guild.
    - Cleans up empty guild roles to keep the server organized.
- **Inactivity Report**: Daily reports on building structures whose owners have been offline for a configurable number of days.
    - Lists owner name, piece count, and last activity date.
    - Includes a `TeleportPlayer` command for easy investigation by admins.
- **Isolated Data Paths**: Each server uses its own separate database for stats, while player identity and VIP status are managed in a unified global registry (`data/global_registry.db`).
- **Robust and Resilient**: Features resilient RCON connection handling to gracefully manage temporary server unavailability.

## Project Structure

The bot is organized into a modular, cog-based architecture for better maintainability and extensibility.

- `bot.py`: The main entry point of the bot, responsible for initialization, loading cogs, and database setup.
- `cogs/`: This directory contains individual cogs, each encapsulating specific features.
- `utils/`: Contains shared utility modules like database interactions and log parsing.
- `data/`: Contains the SQLite databases. `global_registry.db` stores identities and VIPs, while `playertracker_*.db` store server-specific stats.
- `logs/`: Contains reward log files.
- `locale/`: Contains language translation files.
- `scripts/`: Contains utility scripts for RCON diagnosis and testing.
- `sql/`: Contains SQL scripts used by features like the Building Watcher.
- `.env`: A file for storing sensitive information like your bot token and RCON passwords. This file is not committed to version control.
- `.env.example`: A template for the `.env` file.
- `config.py`: The main configuration file. This should not be committed to version control.
- `config.py.example`: A template for `config.py`.
- `tests/`: Contains the test suite for the bot.

## Installation

**1. Clone the Repository**
```bash
git clone https://github.com/melecajou/conanserverstatus.git
cd conanserverstatus
```

**2. Create a Virtual Environment (Recommended)**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install Dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure the Bot**

**a. Discord Portal Setup:**
1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Select your application and go to the **Bot** tab.
3.  Under **Privileged Gateway Intents**, enable:
    - **Server Members Intent** (Required for Guild Sync and Role Assignment).
    - **Message Content Intent** (Required for reading in-game chat commands).

**b. Create the `.env` file:**
Copy the example file to create your own `.env` file.
```bash
cp .env.example .env
```
Now, open the `.env` file and fill in your `STATUS_BOT_TOKEN` and the `RCON_PASS` for each of your servers.

**b. Create the `config.py` file:**
Copy the example file to create your own `config.py` file.
```bash
cp config.py.example config.py
```
Inside `config.py`, you will need to fill in the bot's `LANGUAGE` and the `SERVERS` list with the details of your game servers. The bot token and RCON passwords will be loaded automatically from your `.env` file.

**Bot Language Configuration:**
Set the `LANGUAGE` variable at the top of `config.py`. For example:
```python
LANGUAGE = "pt_BR" # or "en" for English
```

**Cluster Status Configuration:**
To enable a consolidated status message for all your servers:
1.  In `config.py`, set `CLUSTER_STATUS["ENABLED"]` to `True`.
2.  Set `CLUSTER_STATUS["CHANNEL_ID"]` to the ID of the Discord channel where you want the consolidated status to appear.
3.  (Optional) Add an `"ALIAS"` key to each server in the `SERVERS` list to provide a shorter name for the cluster status display.

```python
CLUSTER_STATUS = {
    "ENABLED": True,
    "CHANNEL_ID": 123456789012345678
}
```

**Reward Configuration with VIP Tiers:**
For each server in the `SERVERS` list, update the `REWARD_CONFIG` section to define reward intervals based on VIP levels. An example configuration demonstrating different intervals for VIP levels 0, 1, and 2 is shown below:

```python
            "REWARD_CONFIG": {
                "ENABLED": True,
                # INTERVALS_MINUTES allows different reward intervals based on VIP level.
                # The key 0 represents the default VIP level.
                "INTERVALS_MINUTES": {
                    0: 60,  # Level 0 (Default): Reward every 60 minutes
                    1: 30,  # Level 1 (VIP): Reward every 30 minutes
                    2: 15   # Level 2 (Super VIP): Reward every 15 minutes
                },
                "REWARD_ITEM_ID": 10000000, # Replace with your desired in-game item ID
                "REWARD_QUANTITY": 1        # Replace with the desired quantity
            },
```

**Registered User Role Configuration:**
To automatically assign a role to registered users:
1.  In `config.py`, set `REGISTERED_ROLE_ID` to the ID of the Discord role you want to give.
    ```python
    REGISTERED_ROLE_ID = 123456789012345678
    ```
2.  **Permissions**: Ensure the Bot's own role is **higher** in the Discord server settings > Roles list than the role it is trying to assign. Also, the bot must have the "Manage Roles" permission.
3.  **Syncing**: After configuring this for the first time, run the `/sync_roles` command in Discord (Admin only) to give the role to all users who are already registered.

**Warp System Configuration:**
To enable the warp system:
1.  In `config.py`, add the `WARP_CONFIG` section to your server configuration.
2.  Define `ENABLED` as `True`.
3.  Set the `COOLDOWN_MINUTES`.
4.  Add your destinations in `LOCATIONS` using the format `"name": "X Y Z"`.

```python
            "WARP_CONFIG": {
                "ENABLED": True,
                "COOLDOWN_MINUTES": 5,
                "HOME_ENABLED": True,
                "HOME_COOLDOWN_MINUTES": 15,
                "SETHOME_COOLDOWN_MINUTES": 5,
                "LOCATIONS": {
                    "hub": "10000 20000 5000",
                    "arena": "-5000 10000 2000"
                }
            }
```

**Guild Sync Configuration:**
To enable automatic guild role synchronization:
1.  In `config.py`, add the `GUILD_SYNC` block.
2.  Set `ENABLED` to `True`.
3.  Set `SERVER_ID` to your Discord server ID.
4.  (Optional) Customize the `ROLE_PREFIX`.

```python
GUILD_SYNC = {
    "ENABLED": True,
    "SERVER_ID": 123456789012345678,
    "ROLE_PREFIX": "🛡️ ",
    "CLEANUP_EMPTY_ROLES": True
}
```

**Inactivity Report Configuration:**
To enable daily reports on abandoned bases:
1.  Add the `INACTIVITY_REPORT` block to each server in `config.py`.
2.  Set `ENABLED` to `True`.
3.  Define `DAYS` (threshold for inactivity) and `CHANNEL_ID` (where the admin report will be sent).

```python
            "INACTIVITY_REPORT": {
                "ENABLED": True,
                "DAYS": 15,
                "CHANNEL_ID": 123456789012345678,
                "SQL_PATH": "/home/steam/bots/ConanServerStatus/sql/inactive_structures.sql"
            }
```

**VIP System and Expiration:**
The bot features a hybrid VIP system:
- **Building Benefits**: Once a player is set as VIP (Level > 0), their building piece limit (monitored by the Building Watcher) is increased **permanently**.
- **Reward Benefits**: Playtime reward intervals (faster rewards) can be **temporary**. When using `/setvip`, you can specify the duration in days. After this period, the player's reward interval reverts to the default (Level 0), but they keep their VIP Level for building purposes.

**Important**: When running the bot as a `systemd` service, ensure all file paths in `config.py` (like `DB_PATH`, `SQL_PATH`, etc.) are **absolute paths**, as the service does not run from your home directory.


## Running the Bot as a Service

To ensure the bot runs continuously, create a `systemd` service.

**a. Create the service file:**
```bash
sudo nano /etc/systemd/system/conan_server_status.service
```

**b. Paste the following content.** Adjust `User`, `WorkingDirectory`, and `ExecStart` to match your setup.
```ini
[Unit]
Description=Conan Exiles Server Status Bot
After=network.target

[Service]
User=steam
WorkingDirectory=/home/steam/bots/ConanServerStatus
ExecStart=/home/steam/bots/ConanServerStatus/venv/bin/python bot.py

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**c. Enable and start the service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable conan_server_status.service
sudo systemctl start conan_server_status.service
```
