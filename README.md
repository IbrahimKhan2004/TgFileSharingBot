# TgFileSharingBot

A sophisticated Telegram bot designed to store, manage, and share files with users through a token-based access system. It leverages multiple channels for different functionalities, integrates with TMDB for rich media metadata, and includes advanced features for admin control and automated maintenance.

## Core Concepts & How It Works

The bot operates using a multi-channel system and a token verification process for file access:

1.  **File Ingestion:** The bot owner sends media files to the bot, which are then copied to a private **Database Channel** (`DB_CHANNEL_ID`).
2.  **Processing & Cataloging:** A background task processes each file from a queue, fetches metadata from TMDB, and posts a formatted message (with a "Send in DM" button) to a public-facing **Update Channel** (`UPDATE_CHANNEL_ID`).
3.  **User File Access:** Users browse the Update Channel and click the "Send in DM" button, which deep-links them to the bot with a specific file ID.
4.  **Token Verification:** Before receiving a file, a user must have a valid token. If they don't, they are prompted to get one via a shortened link. This link resolves to a `/start token_<unique_token>` command, verifying their session.
5.  **Access Granted:** Once verified, a user's token is valid for a set duration (`TOKEN_TIMEOUT`) and allows them to download a specific number of files (`DAILY_LIMIT`).

## Features

*   **Token-Based Access Control:**
    *   Users must verify a token to download files.
    *   Tokens have a configurable timeout (`TOKEN_TIMEOUT`).
    *   Each token has a daily download limit (`DAILY_LIMIT`).
    *   Verification links are now valid for **24 hours**, preventing "Invalid ID" errors for users who don't click them immediately.

*   **Automated Background Tasks:**
    *   **Concurrent & Non-Blocking:** All background tasks run in parallel, ensuring the bot remains responsive.
    *   **File Processing Queue:** Handles new files sequentially and reliably.
    *   **Daily Stats Reset:** A restart-proof scheduler resets daily counters at midnight (IST).
    *   **Expired Token Notifications:** Automatically detects expired user tokens and prompts them to re-verify.
    *   **Automatic User Pruning:** A daily task that automatically removes inactive, unverified users (inactive for >40 days) to maintain database hygiene.

*   **Advanced Admin Controls:**
    *   A comprehensive set of commands allows the owner to manage users, content, and the bot itself.
    *   Dynamic, in-chat bot settings configuration via the `/settings` command.
    *   Detailed operational logging to a private **Log Channel** (`LOG_CHANNEL_ID`).

*   **Content Management:**
    *   TMDB integration for fetching movie and show posters.
    *   Force subscription option to require users to join a channel.
    *   Batch indexing of existing files in the database channel.

*   **Robust Error & Bypass Handling:**
    *   Detects and penalizes users attempting to bypass the token verification timer.
    *   Gracefully handles users who have blocked the bot or have deactivated accounts.

## Command List

### User Commands

| Command           | Description                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------- |
| `/start`          | Shows the main welcome message.                                                                         |
| `/me` or `/status`| Displays your current profile, including verification status, token expiry time, and daily file limit. |

### Admin Commands (`OWNER_ID` Only)

| Command                           | Description                                                                                                      |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **User Management**               |                                                                                                                  |
| `/broadcast` (reply to a message) | Sends the replied message to all users of the bot.                                                               |
| `/stats`                          | Shows a detailed summary of bot statistics, including total users, daily activity, uptime, and ping.             |
| `/unban <user_id>`                | Removes a ban from a user, allowing them to use the bot again.                                                     |
| `/verify <user_id>`               | Manually marks a user as verified, granting them immediate access.                                               |
| `/reset_limit <user_id>`          | Resets a user's daily file download count back to zero.                                                          |
| `/expire_token <user_id>`         | Manually expires a user's token, requiring them to re-verify.                                                    |
| **Content Management**            |                                                                                                                  |
| `/index`                          | Starts a batch process to index or re-process files from the `DB_CHANNEL_ID`.                                      |
| `/delete`                         | Prompts for a start and end message ID to delete a range of messages from the `UPDATE_CHANNEL_ID`.               |
| **Bot Management**                |                                                                                                                  |
| `/log`                            | Sends the bot's `log.txt` file to the admin.                                                                     |
| `/settings`                       | Opens an interactive menu to view and change the bot's live configuration.                                       |
| `/restart`                        | Restarts the bot. Can also pull updates from a Git repository if configured.                                     |

## Channel Configuration

To use this bot, you **must** create three Telegram channels and add the bot as an administrator in each:

1.  **`DB_CHANNEL_ID` (Database Channel):** A **private** channel where the bot stores all original media files.
2.  **`UPDATE_CHANNEL_ID` (Updates Channel):** A public or private channel where the bot posts formatted messages about available files.
3.  **`LOG_CHANNEL_ID` (Log Channel):** A **private** channel where the bot sends operational logs, status updates, and error reports.

## Deployment

### Prerequisites

*   Python 3.10+
*   Git
*   MongoDB instance

### Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/TgFileSharingBot.git
    cd TgFileSharingBot
    ```

2.  **Create `config.env`:**
    Copy `config_sample.env` to `config.env` and fill in all the required variables.
    ```bash
    cp config_sample.env config.env
    nano config.env
    ```

3.  **Install dependencies:**
    ```bash
    pip3 install -r requirements.txt
    ```

4.  **Run the bot:**
    The `start.sh` script is used to run both the web server and the bot concurrently.
    ```bash
    sh start.sh
    ```

### Docker Setup

1.  **Prepare `config.env`:** Ensure your `config.env` file is present in the root directory.
2.  **Build the Docker image:**
    ```bash
    docker build -t tgfilesharingbot .
    ```
3.  **Run the Docker container:**
    ```bash
    docker run -d --env-file ./config.env --name filebot tgfilesharingbot
    ```

## Disclaimer

This bot offers powerful file sharing capabilities. Ensure you comply with Telegram's Terms of Service and respect copyright laws. The developers are not responsible for how this bot is used.
