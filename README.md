# Conan Exiles Server Status Bot

This Discord bot monitors the status of one or more Conan Exiles servers. It is designed to be highly configurable, providing real-time updates on server status, online players, and other automated reports directly to your Discord channels.

## Features

- **Multi-Server Monitoring**: Tracks multiple servers simultaneously, each with its own configuration.
- **Efficient Live Status**: Displays an auto-updating list of online players, including their in-game level and total playtime. This process is highly optimized, using asynchronous, non-blocking database queries to ensure minimal performance impact.
- **Robust Playtime Rewards**: A per-server reward system with tiered VIP levels. The system is resilient, featuring a retry mechanism for reward delivery to handle temporary RCON connection issues.
- **Player Registration and Account Linking**: A streamlined process for players to link their in-game character to their Discord account using a `/register` command and an in-game code. This enables personalized features and rewards.
- **Admin Commands**: Provides administrative functionalities, such as setting VIP levels for Discord members (`/setvip @User <level>`), which directly influences their reward intervals and other potential benefits.
- **Isolated Data Paths**: Each server can be configured to use its own separate database and log file, preventing data mix-ups and allowing for independent operation.
- **Robust and Resilient**: Features resilient RCON connection handling to gracefully manage temporary server unavailability.

## Project Structure

The bot is organized into a modular, cog-based architecture for better maintainability and extensibility.

- `bot.py`: The main entry point of the bot, responsible for initialization, loading cogs, and database setup.
- `cogs/`: This directory contains individual cogs, each encapsulating specific features.
- `utils/`: Contains shared utility modules like database interactions and log parsing.
- `data/`: Contains the SQLite databases for player time tracking.
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

**a. Create the `.env` file:**
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
