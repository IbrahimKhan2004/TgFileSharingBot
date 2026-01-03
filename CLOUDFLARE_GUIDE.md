# 🚀 Cloudflare Worker Setup Guide for Direct Download Links

This guide will walk you through setting up a Cloudflare Worker to enable the direct download link feature for your Telegram bot. This worker will handle streaming large files from Telegram directly to users, saving your server's bandwidth and resources.

## Prerequisites

1.  **A Cloudflare Account:** If you don't have one, sign up for a free account at [cloudflare.com](https://cloudflare.com).
2.  **A Domain/Subdomain (Optional but Recommended):** While you can use the default `*.workers.dev` subdomain, a custom domain looks more professional.
3.  **Your Bot Deployed:** Your main bot should already be deployed and running.

---

## Step 1: Create the Cloudflare Worker

1.  **Log in** to your Cloudflare dashboard.
2.  Navigate to **Workers & Pages** from the left sidebar.
3.  Click on **Create application**, then select **Create Worker**.
4.  Give your worker a unique name (e.g., `telegram-file-streamer`). This will be part of its URL.
5.  Click **Deploy**.

---

## Step 2: Configure the Worker Script

1.  After deployment, click **Edit code**.
2.  This will open the Cloudflare Worker code editor.
3.  **Delete** all the boilerplate code that is pre-filled in the editor.
4.  Open the `worker.js` file from this repository.
5.  **Copy** the entire content of `worker.js`.
6.  **Paste** the copied code into the Cloudflare editor.
7.  Click **Deploy** in the top-right corner to save your script.

---

## Step 3: Configure Worker Secrets and Backend URL

This is the most important step. We need to securely tell the worker how to communicate with your bot's web server.

1.  Go back to your worker's dashboard.
2.  Click on the **Settings** tab.
3.  Select **Variables**.
4.  Under **Environment Variables**, we will add two **secrets**. These are encrypted and secure. Click **Add variable** for each:

    *   **Variable 1: Backend URL**
        *   **Variable name:** `BACKEND_URL`
        *   **Value:** Enter the full URL to your bot's web server, for example, `https://your-bot.koyeb.app`. **Do not add a `/` at the end.**
        *   Click **Encrypt**.

    *   **Variable 2: Worker Secret**
        *   **Variable name:** `WORKER_SECRET`
        *   **Value:** Create a strong, random password. You can use a password generator for this. This secret will be used to verify that requests are coming from your worker and not from someone else.
        *   Click **Encrypt**.

5.  After adding both variables, click **Save and deploy**.

---

## Step 4: Update Your Bot's `config.env` File

Now, we need to configure your main bot to use the worker.

1.  Open your `config.env` file.
2.  You will need to fill in the new variables we added:

    *   `CLOUDFLARE_WORKER_URL`:
        *   Go to your worker's main dashboard page in Cloudflare.
        *   You will see the **URL** listed there (e.g., `https://telegram-file-streamer.your-account.workers.dev`).
        *   Copy this URL and paste it as the value.

    *   `ENCRYPTION_KEY`:
        *   This is used to create the secure links. You need a **strong, 32-character-long** random string.
        *   You can use any password generator to create this, or simply type a random string of 32 characters. The bot will handle the rest.
        *   **Example:** `MySuperSecretKeyForMyBotProject32`
        *   Paste this key as the value.

    *   `WORKER_SECRET`:
        *   This **must be the exact same** strong password that you configured in the worker's settings (Step 3, Variable 2).

3.  Your final configuration should look something like this:

    ```env
    # ... other variables ...

    # Cloudflare Worker for Direct Download Links
    CLOUDFLARE_WORKER_URL = "https://telegram-file-streamer.your-account.workers.dev"
    ENCRYPTION_KEY = "your_super_secret_32_character_long_key_here"
    WORKER_SECRET = "your_super_secret_password_for_worker_auth"
    ```

---

## Step 5: Restart Your Bot

1.  After saving the `config.env` file, **restart your bot application**.
2.  The bot will now pick up the new environment variables.

---

## ✅ All Done!

Your bot is now configured to generate secure, high-performance direct download links using Cloudflare Workers. When a user requests a file in their DM, they will see the "🚀 Generate Direct Link" button, which will now function correctly.
