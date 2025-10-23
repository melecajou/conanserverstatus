# Conan Exiles Server Status Bot

This Discord bot monitors the status of one or more Conan Exiles servers. It is designed to be highly configurable, providing real-time updates on server status, online players, and other automated reports directly to your Discord channels.

## Features

- **Multi-Server Monitoring**: Tracks multiple servers simultaneously, each with its own configuration.
- **Efficient Live Status**: Displays an auto-updating list of online players, including their in-game level and total playtime. This process is highly optimized, using batch database queries to ensure minimal performance impact, even with a large number of players.
- **Robust Playtime Rewards**: A per-server reward system with tiered VIP levels. The system is resilient, featuring a retry mechanism for reward delivery to handle temporary RCON connection issues.
- **Player Registration and Account Linking**: A streamlined process for players to link their in-game character to their Discord account using a `/registrar` command and an in-game code. This enables personalized features and rewards.
- **Admin Commands**: Provides administrative functionalities, such as setting VIP levels for Discord members (`/setvip @User <level>`), which directly influences their reward intervals and other potential benefits.
- **Isolated Data Paths**: Each server can be configured to use its own separate database and log file, preventing data mix-ups and allowing for independent operation.
- **Robust and Resilient**: Features RCON connection error handling with automatic retry attempts.

## Project Structure

The bot is organized into a modular, cog-based architecture for better maintainability and extensibility.

- `bot.py`: The main entry point of the bot, responsible for initialization, loading cogs, and database setup.
- `cogs/`: This directory contains individual cogs, each encapsulating specific features:
    - `admin.py`: Provides administrative commands (e.g., setting VIP levels).
    - `announcements.py`: Manages scheduled announcements.
    - `building.py`: Handles automated building reports.
    - `registration.py`: Manages player registration and account linking.
    - `rewards.py`: Tracks player playtime and issues rewards.
    - `status.py`: Manages live server status updates.
- `utils/`: Contains shared utility modules like database interactions, RCON communication, and log parsing.
- `data/`: Contains the SQLite databases for player time tracking.
- `logs/`: Contains reward log files.
- `locale/`: Contains language translation files.
- `config.py`: The main configuration file. **This should not be committed to version control.**
- `config.py.example`: A template for `config.py`.
- `buildings.sql`: The SQL script used by the Building Watcher feature.
- `i18n_setup.py`: Utility for internationalization setup.
- `scripts/`: Contains utility scripts for RCON diagnosis and testing.

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
Copy the example file and fill in your information.
```bash
cp config.py.example config.py
nano config.py
```
Inside `config.py`, you will need to fill in your bot token and the `SERVERS` list. See the comments within the example file for a detailed explanation of all configuration options, including the new `ANNOUNCEMENTS` and `BUILDING_WATCHER` blocks.

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
