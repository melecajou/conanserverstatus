# Conan Exiles Server Status Bot

This Discord bot monitors the status of one or more Conan Exiles servers and displays the information in a specific channel, updating it periodically.

## Features

- Monitors multiple servers simultaneously.
- Displays status (Online/Offline) and the list of connected players.
- Automatically updates the status message at a configurable interval.
- Provides a slash command (`/status`) for manual checking.
- Robust, with error handling and reconnection attempts.

## Languages (Internationalization)

The bot supports multiple languages. Translations are managed by the `gettext` system.

**Supported Languages:**
- `en`: English
- `pt_BR`: Brazilian Portuguese

You can set the desired language in the `config.py` file.

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

It is good practice to isolate project dependencies.

```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install Dependencies**

Install the required Python libraries.

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
- `LANGUAGE`: The language the bot will use. The default is `'en'`. Change to `'pt_BR'` for Portuguese.
- `STATUS_BOT_TOKEN`: Your Discord bot token. **Keep this secret!**
- `SERVERS`: A list with the data for each server you want to monitor (IP, RCON port, RCON password, and status channel ID).

## Running the Bot

**For testing (manual execution):**

You can start the bot directly in your terminal. Press `CTRL+C` to stop.

```bash
python conan_server_status.py
```

**For production (using systemd):**

To ensure the bot runs continuously in the background and restarts with the server, let's create a `systemd` service.

**a. Create the service file:**

```bash
sudo nano /etc/systemd/system/conan_status_bot.service
```

**b. Paste the following content into the file.**

**Important:** Adjust the paths in `WorkingDirectory` and `ExecStart` to match the location where you cloned the repository.

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
sudo systemctl daemon-reload         # Reload systemd to read the new file
sudo systemctl enable conan_status_bot.service # Enable the bot to start with the system
sudo systemctl start conan_status_bot.service  # Start the bot immediately
```

**d. Check the service status:**

```bash
sudo systemctl status conan_status_bot.service
```

## Discord Usage

- The bot will keep an always-updated status message in the channel you configured in `config.py`.
- Any server member can use the `/status` command to get an immediate update for all monitored servers.
