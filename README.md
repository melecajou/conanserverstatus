# Conan Exiles Server Status Bot

This Discord bot monitors the status of one or more Conan Exiles servers and displays the information in a specific channel, updating it periodically.

## Features

- Monitors multiple servers simultaneously.
- Displays status (Online/Offline) and the list of connected players.
- **Displays the in-game level for each online player.**
- **Per-server configurable playtime reward system:**
    - Can be enabled, disabled, or configured independently for each server.
    - Rewards players with a chosen item and quantity.
    - Reward interval (playtime required) is configurable for each server.
- Automatically updates the status message every minute.
- Logs all player rewards to a local `logs/rewards.log` file.
- Robust, with RCON connection error handling and retry attempts.

## Project Structure

The project is organized into the following directories:
- `data/`: Contains the `playertracker.db` SQLite database.
- `logs/`: Contains the `rewards.log` file.
- `locale/`: Contains language translation files.
- `scripts/`: Contains helper and diagnostic scripts.

## Prerequisites

- Python 3.8 or higher
- Git
- A server with internet access to host the bot.

## Installation

Follow the steps below to set up the bot on your server.

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

Inside `config.py`, you will need to fill in:
- `LANGUAGE`: The language the bot will use (`'en'` or `'pt_BR'`).
- `STATUS_BOT_TOKEN`: Your Discord bot token. **Keep this secret!**
- `SERVERS`: A list where each entry contains the configuration for a server you want to monitor. This includes:
    - `NAME`: Display name for the server.
    - `SERVER_IP`: IP of the Conan Exiles server.
    - `RCON_PORT`: RCON port of the server.
    - `RCON_PASS`: RCON password of the server.
    - `STATUS_CHANNEL_ID`: Discord channel ID to post the status.
    - `DB_PATH`: (Optional) Absolute path to the `game.db` file to show player levels.
    - `REWARD_CONFIG`: (Optional) A block of settings to control the reward system *for this specific server*. You can enable/disable it, set the item, quantity, and required playtime.

## Running the Bot

**For testing (manual execution):**

You can start the bot directly in your terminal. Press `CTRL+C` to stop.

```bash
python conan_server_status.py
```

**For production (using systemd):**

To ensure the bot runs continuously, create a `systemd` service.

**a. Create the service file:**

```bash
sudo nano /etc/systemd/system/conan_status_bot.service
```

**b. Paste the following content.** **Important:** Adjust `User`, `Group`, `WorkingDirectory`, and `ExecStart` to match your setup.

```ini
[Unit]
Description=Conan Exiles Server Status Bot
After=network.target

[Service]
User=your_user          # <-- CHANGE TO YOUR USERNAME (e.g., steam)
Group=your_group         # <-- CHANGE TO YOUR GROUP (e.g., steam)

WorkingDirectory=/home/your_user/bots/ConanServerStatus  # <-- ADJUST THE PATH
ExecStart=/home/your_user/bots/ConanServerStatus/venv/bin/python conan_server_status.py # <-- ADJUST THE PATH

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**c. Enable and start the service:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable conan_status_bot.service
sudo systemctl start conan_status_bot.service
```

**d. Check the service status:**

```bash
sudo systemctl status conan_status_bot.service
```

## Discord Usage

- The bot will maintain an always-updated status message in the channel(s) you configured in `config.py`. There are no user-facing commands; the bot's operation is entirely automatic.