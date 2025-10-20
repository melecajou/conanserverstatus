# Conan Exiles Server Status Bot

This Discord bot monitors the status of one or more Conan Exiles servers. It is designed to be highly configurable, providing real-time updates on server status, online players, and other automated reports directly to your Discord channels.

## Features

- **Multi-Server Monitoring**: Tracks multiple servers simultaneously, each with its own configuration.
- **Live Player Status**: Displays an auto-updating list of online players, including their in-game level and total playtime on the server.
- **Live System Stats**: Extracts and displays live server performance metrics (Uptime, Server FPS, Memory Usage, CPU) directly in the status embed.
- **Configurable Playtime Rewards**: A per-server reward system that can be enabled or disabled. You can configure the playtime interval, reward item, and quantity for each server independently.
- **Scheduled Announcements**: A per-server announcement system to post messages to a specific channel on a schedule (e.g., "Double XP enabled!"). You can configure the day, time, message, and timezone for each server.
- **Automated Building Reports**: An hourly task that queries a backup of the game database to generate a report of building piece counts for all players and clans. It highlights those who are over a configurable limit, helping to enforce server rules safely.
- **Isolated Data Paths**: Each server can be configured to use its own separate database and log file, preventing data mix-ups and allowing for independent operation.
- **Robust and Resilient**: Features RCON connection error handling with automatic retry attempts.

## Project Structure

- `data/`: Contains the SQLite databases for player time tracking.
- `logs/`: Contains reward log files.
- `locale/`: Contains language translation files.
- `conan_server_status.py`: The main bot application.
- `config.py`: The main configuration file. **This should not be committed to version control.**
- `config.py.example`: A template for `config.py`.
- `buildings.sql`: The SQL script used by the Building Watcher feature.

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
ExecStart=/home/steam/bots/ConanServerStatus/venv/bin/python conan_server_status.py

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
