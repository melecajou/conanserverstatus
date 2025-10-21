# Summary of Bot Modifications

This document summarizes the recent changes and development process for the Conan Server Status bot, which has transitioned to a modular, cog-based architecture.

## Phase 1-3: Initial Features & Hardening

The initial phases focused on creating a robust bot that could monitor server status, display player levels, and implement a configurable playtime reward system. This included adding RCON stability, extensive configuration options, and organizing the project structure.

## Phase 4: Advanced Automation and Reporting (Cog-based Implementation)

This phase focused on adding powerful, automated features to assist with server management and player communication, now implemented as Discord.py cogs.

1.  **Data Isolation for PvP Server**: To prepare for a server wipe and separate operations, the bot was modified to allow per-server database and log file paths. The PvP server was configured to use its own `playertracker_pvp.db` and `rewards_pvp.log`, completely isolating its data from the other servers.

2.  **Scheduled Announcements (`AnnouncementsCog`)**: A new cog was created to send automated, scheduled messages to Discord. This feature is fully configurable on a per-server basis via the `ANNOUNCEMENTS` block in `config.py`, allowing for unique messages, channels, and schedules for each server.

3.  **Player Playtime Display**: The main status embed was enhanced to show the total playtime for each currently online player (e.g., "2h 15m"), pulling data from the existing player tracking database.

4.  **Automated Building Watcher (`BuildingCog`)**: A major new feature was added to help enforce server building limits.
    *   **Safe Database Querying**: After extensive debugging, a process was established to safely query building data. The task creates a temporary copy of the game database backup to avoid any risk to the live server and to allow for write operations like creating a `VIEW`.
    *   **SQL Script**: A SQL script (`buildings.sql`) was developed to query the game database and aggregate the number of building pieces per owner.
    *   **Automated Hourly Reports**: A new background task runs every hour to execute the SQL script and post a formatted report to a dedicated Discord channel. The report lists all owners and their piece counts, and automatically flags any that are over the configured build limit.

5.  **Player Registration and Account Linking (`RegistrationCog`)**: A new cog was introduced to allow players to link their in-game characters to their Discord accounts. This involves generating a unique code for in-game entry and monitoring server logs to complete the linking process.

6.  **Admin Commands (`AdminCog`)**: An admin cog was added to provide administrative functionalities, such as setting VIP levels for Discord members, which can influence reward intervals.

7.  **Systemd and Pathing Fixes**: During the implementation of the Building Watcher, a critical `FileNotFoundError` was diagnosed. The issue was traced to the bot using relative paths while being run as a `systemd` service. The fix was to update all relevant paths in `config.py` to be absolute, ensuring the bot can locate its files regardless of its working directory.

## Phase 5: System Status Display (`StatusCog` Enhancement)

The `StatusCog` was enhanced to parse the server's `ConanSandbox.log` file in real-time. The bot now extracts key performance metrics (Uptime, Server FPS, Memory, CPU) and displays them directly in the main status embed, providing an at-a-glance overview of the server's health. This involved adding a new `LOG_PATH` configuration, implementing robust log parsing with regex, and a significant debugging effort to resolve intermittent errors and variable shadowing. The new UI elements were also fully internationalized.