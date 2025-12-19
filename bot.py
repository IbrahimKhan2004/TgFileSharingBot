import uvloop
import asyncio
import uuid
import sys
from time import time as tm
from asyncio import create_subprocess_exec, gather
from pyrogram.types import User
from pyrogram import Client, enums, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, WebpageCurlFailed, WebpageMediaEmpty, MessageNotModified, UserNotParticipant
from asyncio import Queue
from config import *
from utils import *
from tmdb import get_by_name
from shorterner import shorten_url
from database import (
    add_user, del_user, full_userbase, present_user,
    ban_user, is_user_banned, unban_user,
    get_bypass_attempts, increment_bypass_attempts,
    update_user_data, get_user_data, increment_file_count, load_all_user_data,
    reset_daily_stats_v2, save_shortener_link, get_dynamic_config, update_dynamic_config,
    get_expired_users, increment_verified_today, increment_files_shared_today, get_daily_stats,
    get_inactive_unverified_users, delete_users_bulk
)
import urllib.parse
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Define an async queue to handle messages sequentially
message_queue = Queue()

user_data = {}
bot_config = {}
bot_start_time = tm()

def clean_force_sub_url(url_str):
    if not url_str:
        return None
    url_str = str(url_str).strip()
    if url_str.isdigit() or (url_str.startswith("-100") and url_str[4:].isdigit()):
         return int(url_str)

    # Simple regex to strip common URL prefixes
    # t.me/, telegram.me/, telegram.dog/, https://...
    if "/" in url_str:
        return url_str.split("/")[-1]

    return url_str

# PROGRAM BOT INITIALIZATION 

async def load_initial_data():
    global user_data, bot_config
    user_data = await load_all_user_data()

    # Load dynamic config
    db_config = await get_dynamic_config()

    # Initialize with env vars as defaults, override with DB values
    bot_config = {
        'MINIMUM_DURATION': int(db_config.get('MINIMUM_DURATION', MINIMUM_DURATION)),
        'SHORTERNER_URL': db_config.get('SHORTERNER_URL', SHORTERNER_URL),
        'URLSHORTX_API_TOKEN': db_config.get('URLSHORTX_API_TOKEN', URLSHORTX_API_TOKEN),
        'TUT_ID': int(db_config.get('TUT_ID', TUT_ID)),
        'DAILY_LIMIT': int(db_config.get('DAILY_LIMIT', DAILY_LIMIT)),
        'TOKEN_TIMEOUT': int(db_config.get('TOKEN_TIMEOUT', TOKEN_TIMEOUT)),
        'FORCE_SUB_CHANNEL': clean_force_sub_url(db_config.get('FORCE_SUB_CHANNEL', FORCE_SUB_CHANNEL)),
        'AUTO_DELETE_TIME': int(db_config.get('AUTO_DELETE_TIME', AUTO_DELETE_TIME))
    }

    logger.info("Successfully loaded all user data and dynamic config from the database.")

bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1000,
    parse_mode=enums.ParseMode.HTML
).start()

bot_loop = bot.loop
bot_username = bot.me.username

@bot.on_message(filters.private & filters.command("start"))
async def start_command(client, message):
    try:
        user_id = message.from_user.id

        if not await check_force_sub(client, message, user_id):
            return

        if not await present_user(user_id):
            try:
                await add_user(user_id)
            except:
                pass
        
        if await is_user_banned(user_id):
            await message.reply_text("You are currently banned from using this bot. Please try again later.")
            return

        user_link = await get_user_link(message.from_user)

        if len(message.command) > 1:
            command_arg = message.command[1]
            
            # Handle token flow
            if command_arg == "token":
                tut_id = bot_config.get('TUT_ID', TUT_ID)
                msg = await safe_api_call(lambda: bot.get_messages(LOG_CHANNEL_ID, tut_id))
                sent_msg = await safe_api_call(lambda: msg.copy(chat_id=message.chat.id))
                await safe_api_call(lambda: message.delete())
                await asyncio.sleep(300)
                await safe_api_call(lambda: sent_msg.delete())
                return

            # Handle token verification
            if command_arg.startswith("token_"):
                input_token = command_arg[6:]
                
                if user_data.get(user_id, {}).get('status') == 'verified':
                    reply = await safe_api_call(lambda: message.reply_text("You are already verified! ✅"))
                    await auto_delete_message(message, reply)
                    return

                # Bypass detection logic
                if user_id in user_data and 'inittime' in user_data[user_id]:
                    inittime = user_data[user_id]['inittime']
                    duration = tm() - inittime
                    min_duration = bot_config.get('MINIMUM_DURATION', MINIMUM_DURATION)
                    if min_duration and (duration < min_duration):
                        await increment_bypass_attempts(user_id)
                        attempts = await get_bypass_attempts(user_id)

                        ban_duration = 0
                        ban_message = ""

                        if attempts == 1:
                            # 1st bypass: Warning
                            warning_message = (
                                f"<b>First Warning! ⚠️</b>\n\n"
                                f"This is your first warning for attempting to bypass the verification process. "
                                f"Please follow the proper steps. Further attempts will result in a ban."
                            )
                            reply = await safe_api_call(lambda: message.reply_text(warning_message))
                            await auto_delete_message(message, reply)
                            return
                        elif attempts == 2:
                            # 2nd bypass: 15-minute ban
                            ban_duration = 15 * 60  # 15 minutes
                            ban_message = "BANNED for 15 Minutes"
                        elif attempts == 3:
                            # 3rd bypass: 1-hour ban
                            ban_duration = 60 * 60  # 1 hour
                            ban_message = "BANNED for 1 Hour"
                        elif attempts == 4:
                            # 4th bypass: 12-hour ban
                            ban_duration = 12 * 60 * 60  # 12 hours
                            ban_message = "BANNED for 12 Hours"
                        else:
                            # 5th or more bypass: 1-day ban
                            ban_duration = 24 * 60 * 60  # 1 day
                            ban_message = "BANNED for 1 Day"

                        await ban_user(user_id, ban_duration)
                        
                        # Reset user data in database after banning
                        await update_user_data(user_id, {'status': 'unverified', 'time': 0, 'file_count': 0})
                        user_data[user_id] = await get_user_data(user_id) # Refresh local cache

                        log_message = (
                            f"User🕵️‍♂️{user_link} with 🆔 {user_id} @{bot_username} "
                            f"attempted token bypass! ❌ <b>{ban_message}</b> (Attempt: {attempts})\n"
                            f"Time taken: {duration:.2f} seconds (Min required: {min_duration} seconds)\n"
                            f"Token: <code>{input_token}</code>"
                        )
                        await safe_api_call(lambda: bot.send_message(LOG_CHANNEL_ID, log_message, parse_mode=enums.ParseMode.HTML))
                        
                        warning_message = (
                            f"<b>Bypass Detected! 🚨</b>\n\n"
                            f"You have been <b>{ban_message}</b> for repeatedly attempting to bypass the verification process. "
                            f"Your token has been invalidated."
                        )
                        reply = await safe_api_call(lambda: message.reply_text(warning_message))
                        await auto_delete_message(message, reply)
                        return
                
                token_msg = await verify_token(user_id, input_token)
                reply = await safe_api_call(lambda: message.reply_text(token_msg))
                await safe_api_call(lambda: bot.send_message(LOG_CHANNEL_ID, f"User🕵️‍♂️{user_link} with 🆔 {user_id} @{bot_username} {token_msg}", parse_mode=enums.ParseMode.HTML))
                await auto_delete_message(message, reply)
                return

            # Handle file flow
            file_id = int(command_arg)
            if not await check_access(message, user_id):
                return

            file_message = await safe_api_call(lambda: bot.get_messages(DB_CHANNEL_ID, file_id))
            media = file_message.video or file_message.audio or file_message.document
            if media:
                caption = await remove_extension(file_message.caption.html or "")
                auto_delete_time = bot_config.get('AUTO_DELETE_TIME', 60)
                warning = f"\n\n<b>⚠️ This file will be deleted in {auto_delete_time} seconds!</b>"
                copy_message = await safe_api_call(lambda: file_message.copy(chat_id=message.chat.id, caption=f"<b>{caption}</b>{warning}", parse_mode=enums.ParseMode.HTML))
                await increment_file_count(user_id)
                await increment_files_shared_today() # New line to track daily file shares
                user_data[user_id]['file_count'] += 1

                # File Limit Warning Logic
                daily_limit = bot_config.get('DAILY_LIMIT', DAILY_LIMIT)
                current_count = user_data[user_id]['file_count']
                warning_threshold = int(daily_limit * 0.8)

                if current_count == warning_threshold:
                    try:
                        remaining = daily_limit - current_count
                        warning_msg = await bot.send_message(
                            user_id,
                            f"⚠️ <b>File Limit Warning</b>\n\nYou are approaching your download limit. You have {remaining} downloads left on your current token."
                        )
                        # Auto-delete the warning after a while to avoid clutter
                        asyncio.create_task(auto_delete_message(message, warning_msg, 60))
                    except Exception as e:
                        logger.warning(f"Failed to send file limit warning to user {user_id}: {e}")

                await auto_delete_message(message, copy_message, auto_delete_time)
            else:
                await auto_delete_message(message, await message.reply_text("File not found or inaccessible."))
            return

        # Default flow (no arguments)
        await greet_user(message)
        
    except ValueError:
        reply = await safe_api_call(lambda: message.reply_text("Invalid File ID."))
        await auto_delete_message(message, reply)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await auto_delete_message(message, await message.reply_text(f"An error occurred: {e}"))


@bot.on_message(filters.chat(DB_CHANNEL_ID) & (filters.document | filters.video | filters.audio | filters.sticker))
async def handle_new_message(client, message):
    # Add the message to the queue for sequential processing
    await message_queue.put(message)
    
@bot.on_message(filters.private & filters.command("index") & filters.user(OWNER_ID))
async def handle_file(client, message):
    try:
        user_id = message.from_user.id

        # Helper function to get user input
        async def get_user_input(prompt):
            bot_message = await message.reply_text(prompt)
            user_message = await bot.listen(chat_id=message.chat.id, filters=filters.user(OWNER_ID))
            asyncio.create_task(auto_delete_message(bot_message, user_message))
            return await extract_tg_link(user_message.text.strip())

        async def auto_delete_message(bot_message, user_message):
            await asyncio.sleep(10)
            await bot_message.delete()
            await user_message.delete()

        # Get the start and end message IDs
        start_msg_id = int(await get_user_input("Send first msg link"))
        end_msg_id = int(await get_user_input("Send end msg link"))

        batch_size = 199

        for start in range(int(start_msg_id), int(end_msg_id) + 1, batch_size):            
            end = min(start + batch_size - 1, int(end_msg_id))
            file_messages = await bot.get_messages(DB_CHANNEL_ID, range(start, end + 1))

            for file_message in file_messages:
                await message_queue.put(file_message)

    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

@bot.on_message(filters.private & filters.command("delete") & filters.user(OWNER_ID))
async def delete_messages_command(client, message):
    try:
        user_id = message.from_user.id

        # Helper function to get user input
        async def get_user_input(prompt):
            bot_message = await message.reply_text(prompt)
            user_message = await bot.listen(chat_id=message.chat.id, filters=filters.user(OWNER_ID))
            asyncio.create_task(auto_delete_message(bot_message, user_message))
            return await extract_tg_link(user_message.text.strip())

        # Get the start and end message IDs from the user
        start_msg_id = int(await get_user_input("Send the link of the first message you want to delete (from UPDATE_CHANNEL_ID):"))
        end_msg_id = int(await get_user_input("Send the link of the last message you want to delete (from UPDATE_CHANNEL_ID):"))

        deleted_count = 0
        batch_size = 99  # Pyrogram allows deleting up to 100 messages at once

        for i in range(start_msg_id, end_msg_id + 1, batch_size):
            messages_to_delete = []
            for msg_id in range(i, min(i + batch_size, end_msg_id + 1)):
                messages_to_delete.append(msg_id)
            
            if messages_to_delete:
                try:
                    await safe_api_call(lambda: client.delete_messages(chat_id=UPDATE_CHANNEL_ID, message_ids=messages_to_delete))
                    deleted_count += len(messages_to_delete)
                    await message.reply_text(f"Messages {messages_to_delete[0]} to {messages_to_delete[-1]} deleted.")
                except Exception as e:
                    await message.reply_text(f"Error deleting messages: {e}")
                    logger.error(f"Error deleting messages: {e}")

        await message.reply_text(f"Successfully deleted {deleted_count} messages from UPDATE_CHANNEL_ID.")

    except ValueError:
        await message.reply_text("Invalid message ID. Please provide only numerical message IDs or valid Telegram links.")
    except Exception as e:
        logger.error(f"Error in delete command: {e}")
        await message.reply_text(f"An error occurred: {e}")

@bot.on_message(filters.private & filters.command('broadcast') & filters.user(OWNER_ID))
async def send_text(client, message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        logger.info(f"Starting broadcast to {len(query)} users.")
        
        progress_interval = 25 

        for chat_id in query:
            if total > 0 and total % progress_interval == 0:
                logger.info(
                    f"Broadcast progress: Sent to {total}/{len(query)} users. "
                    f"Successful: {successful}, Blocked: {blocked}, Deleted: {deleted}, Unsuccessful: {unsuccessful}"
                )

            try:
                await asyncio.sleep(3)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.x} seconds.")
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                logger.info(f"User {chat_id} is blocked. Removing from DB.")
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                logger.info(f"User {chat_id} is deactivated. Removing from DB.")
                await del_user(chat_id)
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to send message to {chat_id}: {e}")
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""

        logger.info(f"Broadcast finished. Summary: Total={total}, Successful={successful}, Blocked={blocked}, Deleted={deleted}, Unsuccessful={unsuccessful}")
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply("<code>Use this command as a replay to any telegram message with out any spaces.</code>")
        await asyncio.sleep(8)
        await msg.delete()

@bot.on_message(filters.command('stats') & filters.private & filters.user(OWNER_ID))
async def get_stats(client, message):
    start_time = tm()
    msg = await client.send_message(chat_id=message.chat.id, text="Gathering statistics...")

    # Get total users from the database
    users = await full_userbase()
    total_users = len(users)

    # Get daily stats
    daily_stats_data = await get_daily_stats()
    verified_today = daily_stats_data.get('verified_today', 0)
    files_shared_today = daily_stats_data.get('files_shared_today', 0)

    token_timeout = bot_config.get('TOKEN_TIMEOUT', TOKEN_TIMEOUT)
    daily_limit = bot_config.get('DAILY_LIMIT', DAILY_LIMIT)

    # Calculate Uptime
    uptime = get_readable_time(tm() - bot_start_time)

    # Calculate Ping
    end_time = tm()
    ping = f"{(end_time - start_time) * 1000:.2f} ms"

    stats_text = (
        "📊 <b>BOT STATISTICS</b> 📊\n\n"
        f"<b>Total Users:</b> <code>{total_users}</code>\n\n"
        "<b>Today's Stats (Resets at Midnight)</b>\n"
        f"<b>New Verifications Today:</b> <code>{verified_today}</code>\n"
        f"<b>Files Shared Today:</b> <code>{files_shared_today}</code>\n\n"
        f"<b>Token Timeout:</b> <code>{get_readable_time(token_timeout)}</code>\n"
        f"<b>Daily File Limit:</b> <code>{daily_limit}</code> files\n"
        f"<b>Bot Uptime:</b> <code>{uptime}</code>\n"
        f"<b>Ping:</b> <code>{ping}</code>"
    )

    try:
        await msg.edit(stats_text)
    except MessageNotModified:
        pass # Ignore if the message content is the same

@bot.on_message(filters.command("log") & filters.user(OWNER_ID))
async def log_command(client, message):
    user_id = message.from_user.id

    try:
        reply = await bot.send_document(user_id, document=LOG_FILE_NAME, caption="Bot Log File")
        await auto_delete_message(message, reply)
    except Exception as e:
        await bot.send_message(user_id, f"Failed to send log file. Error: {str(e)}")

@bot.on_message(filters.private & filters.command("unban") & filters.user(OWNER_ID))
async def unban_command(client, message):
    try:
        if len(message.command) > 1:
            user_id_to_unban = int(message.command[1])
            await unban_user(user_id_to_unban)
            await message.reply_text(f"User {user_id_to_unban} has been unbanned.")

            # Notify the unbanned user
            await bot.send_message(
                user_id_to_unban,
                "You have been unbanned by the admin. You can now use the bot again."
            )
        else:
            await message.reply_text("Please provide a user ID to unban. Usage: /unban USER_ID")
    except ValueError:
        await message.reply_text("Invalid user ID format.")
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

@bot.on_message(filters.command(["me", "status"]) & filters.private)
async def my_status(client, message):
    user_id = message.from_user.id
    udata = user_data.get(user_id)

    if not udata:
        udata = await get_user_data(user_id)
        if udata:
            user_data[user_id] = udata

    if not udata:
        await message.reply_text("User data not found. Please /start the bot first.")
        return

    status = udata.get('status', 'unverified')
    file_count = udata.get('file_count', 0)
    token_time = udata.get('time', 0)

    daily_limit = bot_config.get('DAILY_LIMIT', DAILY_LIMIT)
    token_timeout = bot_config.get('TOKEN_TIMEOUT', TOKEN_TIMEOUT)

    user_link = await get_user_link(message.from_user)

    status_text = "Verified ✅" if status == "verified" else "Unverified ❌"

    expiry_text = "N/A"
    if status == "verified":
        expiry_time = token_time + token_timeout
        remaining_seconds = expiry_time - tm()

        if remaining_seconds > 0:
            expiry_text = get_readable_time(remaining_seconds)
        else:
            expiry_text = "Expired"
            status_text = "Expired ⚠️"

    response = (
        f"👤 <b>User Profile</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"👤 <b>Name:</b> {user_link}\n\n"
        f"🔐 <b>Status:</b> {status_text}\n"
        f"⏳ <b>Expires in:</b> {expiry_text}\n"
        f"📂 <b>Daily Limit:</b> {file_count}/{daily_limit}"
    )

    await message.reply_text(response)

@bot.on_message(filters.command("settings") & filters.user(OWNER_ID))
async def settings_command(client, message):
    buttons = [
        [InlineKeyboardButton(f"Min Duration: {bot_config.get('MINIMUM_DURATION')}s", callback_data="set_duration")],
        [InlineKeyboardButton(f"Shortener URL: {bot_config.get('SHORTERNER_URL')}", callback_data="set_shortener")],
        [InlineKeyboardButton(f"API Token: {bot_config.get('URLSHORTX_API_TOKEN')}", callback_data="set_api_token")],
        [InlineKeyboardButton(f"Tutorial ID: {bot_config.get('TUT_ID')}", callback_data="set_tut_id")],
        [InlineKeyboardButton(f"Daily Limit: {bot_config.get('DAILY_LIMIT')}", callback_data="set_daily_limit")],
        [InlineKeyboardButton(f"Token Timeout: {bot_config.get('TOKEN_TIMEOUT')}s", callback_data="set_token_timeout")],
        [InlineKeyboardButton(f"Force Sub: {bot_config.get('FORCE_SUB_CHANNEL', 'Not Set')}", callback_data="set_force_sub")],
        [InlineKeyboardButton(f"Auto Delete: {bot_config.get('AUTO_DELETE_TIME')}s", callback_data="set_auto_delete")],
        [InlineKeyboardButton("🔄 Restart Bot", callback_data="restart_bot")],
        [InlineKeyboardButton("❌ Close", callback_data="close_settings")]
    ]
    await message.reply_text("⚙️ <b>Bot Settings</b>\nClick to edit values:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^set_"))
async def settings_callback(client, callback_query):
    action = callback_query.data

    if action == "set_duration":
        prompt = "Send new <b>Minimum Duration</b> (in seconds):"
    elif action == "set_shortener":
        prompt = "Send new <b>Shortener URL</b> (domain):"
    elif action == "set_api_token":
        prompt = "Send new <b>API Token</b>:"
    elif action == "set_tut_id":
        prompt = "Send new <b>Tutorial Message ID</b>:"
    elif action == "set_daily_limit":
        prompt = "Send new <b>Daily Limit</b> (number of files):"
    elif action == "set_token_timeout":
        prompt = "Send new <b>Token Timeout</b> (in seconds):"
    elif action == "set_force_sub":
        prompt = "Send new <b>Force Sub Channel</b> (ID or Username/Link). Send '0' or 'None' to disable:"
    elif action == "set_auto_delete":
        prompt = "Send new <b>Auto Delete Time</b> (in seconds):"
    else:
        return

    await callback_query.message.delete()
    prompt_msg = await client.send_message(callback_query.from_user.id, prompt)

    try:
        user_response = await client.listen(chat_id=callback_query.from_user.id, user_id=callback_query.from_user.id, timeout=60)

        # Check if the user sent a command (e.g. /settings) instead of a value
        if user_response.text and user_response.text.startswith("/"):
            await prompt_msg.edit("❌ Input cancelled. You sent a command.")
            # Process the command normally by re-triggering (or just let the user send it again)
            # Since listen consumes the message, the bot won't process it as a command automatically
            # unless we manually re-dispatch or just tell user to retry.
            # Here we just cancel the setting update.
            return

        new_value = user_response.text.strip()

        # Validation and Update
        key = None
        if action == "set_duration":
            if new_value.isdigit():
                key = 'MINIMUM_DURATION'
                new_value = int(new_value)
            else:
                await callback_query.message.reply_text("Invalid number.")
                return
        elif action == "set_shortener":
            key = 'SHORTERNER_URL'
        elif action == "set_api_token":
            key = 'URLSHORTX_API_TOKEN'
        elif action == "set_tut_id":
             if new_value.isdigit():
                key = 'TUT_ID'
                new_value = int(new_value)
             else:
                await callback_query.message.reply_text("Invalid ID.")
                return
        elif action == "set_daily_limit":
            if new_value.isdigit():
                key = 'DAILY_LIMIT'
                new_value = int(new_value)
            else:
                await callback_query.message.reply_text("Invalid number.")
                return
        elif action == "set_token_timeout":
            if new_value.isdigit():
                key = 'TOKEN_TIMEOUT'
                new_value = int(new_value)
            else:
                await callback_query.message.reply_text("Invalid number.")
                return
        elif action == "set_force_sub":
            if new_value.lower() in ['0', 'none', 'null', '']:
                new_value = None
            else:
                new_value = clean_force_sub_url(new_value)
            key = 'FORCE_SUB_CHANNEL'
        elif action == "set_auto_delete":
            if new_value.isdigit():
                key = 'AUTO_DELETE_TIME'
                new_value = int(new_value)
            else:
                 await callback_query.message.reply_text("Invalid number.")
                 return

        if key:
            await update_dynamic_config(key, new_value)
            bot_config[key] = new_value # Update runtime config
            display_value = new_value if new_value is not None else "Not Set"
            await user_response.reply_text(f"✅ <b>{key}</b> updated to <code>{display_value}</code>.\nRestart required for some changes to fully take effect in other modules.")

            # Show settings again
            await settings_command(client, user_response)

    except asyncio.TimeoutError:
        await prompt_msg.edit("❌ Timed out.")

@bot.on_callback_query(filters.regex("^restart_bot"))
async def restart_callback(client, callback_query):
    await callback_query.answer("Restarting...", show_alert=True)
    os.system("python3 update.py")
    os.execl(sys.executable, sys.executable, "bot.py")

@bot.on_callback_query(filters.regex("^close_settings"))
async def close_settings_callback(client, callback_query):
    await callback_query.message.delete()


@bot.on_message(filters.private & filters.command("verify") & filters.user(OWNER_ID))
async def verify_command(client, message):
    try:
        if len(message.command) > 1:
            user_id_to_verify = int(message.command[1])

            # Check if user exists (optional, but good practice)
            if not await present_user(user_id_to_verify):
                # If user doesn't exist, we might want to add them or just warn.
                # For now, let's just warn as verifying a non-existent user might be weird.
                # But to be safe, we can try to add then verify.
                try:
                    await add_user(user_id_to_verify)
                except:
                    pass

            current_time = tm()
            # Determine token (dummy token for manual verification)
            token = str(uuid.uuid4())

            new_data = {
                "token": token,
                "time": current_time,
                "status": "verified",
                "file_count": 0,
                "inittime": current_time
            }

            await update_user_data(user_id_to_verify, new_data)

            # Update local cache if available
            if user_id_to_verify in user_data:
                 user_data[user_id_to_verify] = {**user_data.get(user_id_to_verify, {}), **new_data}
            else:
                 # Load fresh if not in cache
                 user_data[user_id_to_verify] = await get_user_data(user_id_to_verify)

            await message.reply_text(f"User {user_id_to_verify} has been manually verified! ✅")

            # Notify the user
            try:
                await bot.send_message(
                    user_id_to_verify,
                    "You have been verified by the admin! ✅\nYou can now access files."
                )
            except Exception as e:
                await message.reply_text(f"User verified, but failed to send notification: {e}")

        else:
            await message.reply_text("Please provide a user ID to verify. Usage: /verify USER_ID")
    except ValueError:
        await message.reply_text("Invalid user ID format.")
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

@bot.on_message(filters.private & filters.command("reset_limit") & filters.user(OWNER_ID))
async def reset_limit_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide a user ID. Usage: /reset_limit <user_id>")
        return

    try:
        user_id_to_reset = int(message.command[1])
    except ValueError:
        await message.reply_text("Invalid User ID format.")
        return

    # Check if the user exists in the database
    if not await present_user(user_id_to_reset):
        await message.reply_text(f"❌ Error: User {user_id_to_reset} not found. They must start the bot at least once.")
        return

    # Check if the user is banned
    if await is_user_banned(user_id_to_reset):
        await message.reply_text(f"❌ Error: Cannot reset limit for User {user_id_to_reset} because they are currently banned.")
        return

    # Reset the file count
    await update_user_data(user_id_to_reset, {'file_count': 0})
    if user_id_to_reset in user_data:
        user_data[user_id_to_reset]['file_count'] = 0

    admin_confirmation = f"✅ User {user_id_to_reset}'s file limit has been reset to 0."

    # Try to notify the user
    try:
        await bot.send_message(
            user_id_to_reset,
            "🎉 Good news! An admin has reset your daily file limit. You can continue downloading files."
        )
    except (UserIsBlocked, InputUserDeactivated):
        admin_confirmation += "\n\n(User could not be notified as they may have blocked the bot)."
    except Exception as e:
        admin_confirmation += f"\n\n(Could not notify user due to an error: {e})."

    await message.reply_text(admin_confirmation)

@bot.on_message(filters.private & filters.command("expire_token") & filters.user(OWNER_ID))
async def expire_token_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide a user ID. Usage: /expire_token <user_id>")
        return

    try:
        user_id_to_expire = int(message.command[1])
    except ValueError:
        await message.reply_text("Invalid User ID format.")
        return

    # Check if the user exists
    if not await present_user(user_id_to_expire):
        await message.reply_text(f"❌ Error: User {user_id_to_expire} not found. They must start the bot at least once.")
        return

    # Check if the user is banned
    if await is_user_banned(user_id_to_expire):
        await message.reply_text(f"❌ Error: Cannot expire token for User {user_id_to_expire} because they are already banned.")
        return

    # Expire the token by updating status and resetting time/file_count
    update_data = {'status': 'unverified', 'time': 0, 'file_count': 0}
    await update_user_data(user_id_to_expire, update_data)
    if user_id_to_expire in user_data:
        user_data[user_id_to_expire].update(update_data)

    admin_confirmation = f"✅ User {user_id_to_expire}'s token has been manually expired."

    # Try to notify the user
    try:
        await bot.send_message(
            user_id_to_expire,
            "❗️ Your token has been manually expired by an admin. You will need to re-verify to continue."
        )
    except (UserIsBlocked, InputUserDeactivated):
        admin_confirmation += "\n\n(User could not be notified as they may have blocked the bot)."
    except Exception as e:
        admin_confirmation += f"\n\n(Could not notify user due to an error: {e})."

    await message.reply_text(admin_confirmation)

async def process_queue():
    logging.info("Task started: process_queue")
    while True:
        message = await message_queue.get()  
        if message is None:  
            break
        await process_message(bot, message) 
        message_queue.task_done()

async def process_message(client, message):

    media = message.document or message.video or message.audio
    poster_url = None
    thumbnail = None

    if media:
        caption = message.caption if message.caption else media.file_name
        file_name = await remove_extension(caption)   
        file_size = humanbytes(media.file_size)
        if message.video:
            duration = TimeFormatter(media.duration * 1000)
            if media.thumbs:
                thumbnail = await safe_api_call(lambda: bot.download_media(media.thumbs[0].file_id))
            else:
                thumbnail = None
        else:
            duration = ""
        if not message.audio: 
            movie_name, release_year = await extract_movie_info(file_name)
            poster_url = await get_by_name(movie_name, release_year)
        if message.audio:
            audio_path = await safe_api_call(lambda: bot.download_media(message.audio.file_id))
            audio_thumb = await get_audio_thumbnail(audio_path)

        file_id = message.id
        v_info = f"<blockquote expandable><b>{file_name}</b></blockquote>\n<blockquote><b>{file_size}</b></blockquote>\n<blockquote><b>{duration}</b></blockquote>"
        if message.audio:
            a_info = f"<blockquote ><b>{media.title}</b></blockquote>\n<blockquote><b>{media.performer}</b></blockquote>"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Send in DM", url=f"https://telegram.dog/{bot_username}?start={file_id}")]])

        try:           
            if poster_url:
                await safe_api_call(lambda: bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=poster_url,
                    caption=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                    ))
            elif thumbnail:
                await safe_api_call(lambda: bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=thumbnail,
                    caption=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                ))
            elif not message.audio:
                await safe_api_call(lambda: bot.send_message(
                    UPDATE_CHANNEL_ID,
                    text=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard 
                    ))
                
            if message.audio:
                await safe_api_call(lambda: bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=audio_thumb,
                    caption=a_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                    ))
                os.remove(audio_path) 

        except (WebpageMediaEmpty, WebpageCurlFailed):
            logger.info(f"{poster_url}")
            await safe_api_call(lambda: bot.send_message(
                UPDATE_CHANNEL_ID,
                text=v_info,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=keyboard
                ))

        except FloodWait as f:
            await asyncio.sleep(f.value)
            await process_message(client, message)

        except Exception as e:
            await safe_api_call(lambda: bot.send_message(OWNER_ID, text=f"Error in Proccessing MSG:{file_name} {e}"))
    
    elif message.sticker:
        await safe_api_call(lambda: message.copy(UPDATE_CHANNEL_ID))


@bot.on_message(filters.command('restart') & filters.private & filters.user(OWNER_ID))
async def restart(client, message):
    os.system("python3 update.py")  
    os.execl(sys.executable, sys.executable, "bot.py")

async def check_force_sub(client, message, user_id):
    force_sub_channel = bot_config.get('FORCE_SUB_CHANNEL')
    if not force_sub_channel:
        return True

    try:
        force_sub_channel = clean_force_sub_url(force_sub_channel)
        user = await client.get_chat_member(force_sub_channel, user_id)
        if user.status == enums.ChatMemberStatus.BANNED:
            await message.reply_text("You are banned from the update channel. Contact admin.")
            return False
        return True
    except UserNotParticipant:
        try:
            invite_link = await client.export_chat_invite_link(force_sub_channel)
        except Exception:
            # Fallback if bot can't export link (maybe public channel)
            if str(force_sub_channel).startswith("-100"):
                 # It's an ID, difficult to guess link if not public/admin
                 invite_link = "Please contact admin for link."
            else:
                 # It's likely a username
                 invite_link = f"https://t.me/{force_sub_channel}" if not str(force_sub_channel).startswith("http") else force_sub_channel

        join_button = InlineKeyboardButton("📢 Join Channel", url=invite_link)

        # Preserve original start command args
        username = client.me.username or bot_username
        if len(message.command) > 1:
            start_arg = message.command[1]
            try_again_url = f"https://t.me/{username}?start={start_arg}"
        else:
             try_again_url = f"https://t.me/{username}?start=start"

        try_again_button = InlineKeyboardButton("🔄 Try Again", url=try_again_url)

        text = "<b>👋 You must join our channel to use this bot.\n\nPLEASE JOIN OUR CHANNEL TO GET FILES 👇</b>"
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([[join_button], [try_again_button]]),
            parse_mode=enums.ParseMode.HTML
        )
        return False
    except Exception as e:
        logger.error(f"Force sub check error: {e}")
        # In case of error (e.g. invalid channel ID), let the user pass to avoid blocking them completely
        # or notify admin. For now, letting them pass is safer for UX if config is bad.
        return True

async def verify_token(user_id, input_token):
    current_time = tm()
    
    # Get user data from local cache or DB
    udata = user_data.get(user_id)
    if not udata:
        udata = await get_user_data(user_id)
        if not udata:
            return 'Token Mismatched ❌'
        user_data[user_id] = udata

    stored_token = udata.get('token')
    if input_token == stored_token:
        new_token = str(uuid.uuid4())
        new_data = {"token": new_token, "time": current_time, "status": "verified", "file_count": 0, "inittime": current_time}
        await update_user_data(user_id, new_data)
        await increment_verified_today() # New line to track daily verifications
        user_data[user_id] = {**udata, **new_data} # Update local cache
        token_timeout = bot_config.get('TOKEN_TIMEOUT', TOKEN_TIMEOUT)
        return f'Token Verified ✅ (Validity: {get_readable_time(token_timeout)})'
    else:
        return f'Token Mismatched ❌'

async def check_access(message, user_id):
    udata = user_data.get(user_id)
    if not udata:
        udata = await get_user_data(user_id)
        if not udata:
            # This case happens for new users who are not in the DB yet
            button = await genrate_token(user_id)
            send_message = await message.reply_text( 
                                                    text=f"👋 Welcome! Please get a token to access files. 🚀",
                                                    reply_markup=button
                                                    )
            await auto_delete_message(message, send_message)
            return False
        user_data[user_id] = udata

    time = udata.get('time', 0)
    status = udata.get('status', 'unverified')
    file_count = udata.get('file_count', 0)

    token_timeout = bot_config.get('TOKEN_TIMEOUT', TOKEN_TIMEOUT)
    daily_limit = bot_config.get('DAILY_LIMIT', DAILY_LIMIT)

    expiry = time + token_timeout
    current_time = tm()

    if current_time < expiry and status == "verified":
        if file_count < daily_limit:
            return True
        else:
            reply = await message.reply_text(f"You have reached the daily limit. Please wait until the token expires.")
            await auto_delete_message(message, reply)
            return False
    else:
        button = await update_token(user_id)
        send_message = await message.reply_text( 
                                                text=f"👋 Your token has expired. Please get a new token to continue. 🚀",
                                                reply_markup=button
                                                )
        await auto_delete_message(message, send_message)
        return False

async def update_token(user_id):
    try:
        token = str(uuid.uuid4())
        current_time = tm()
        new_data = {"token": token, "time": current_time, "status": "unverified", "file_count": 0, "inittime": current_time}
        await update_user_data(user_id, new_data)
        user_data[user_id] = {**user_data.get(user_id, {}), **new_data} # Update local cache

        # 1. Create the deep link URL for the bot
        bot_deep_link = f'https://telegram.dog/{bot_username}?start=token_{token}'
        
        # 2. Shorten this deep link using the external URL shortener (shorterner.py)
        external_shortened_url = await shorten_url(
            bot_deep_link,
            base_site=bot_config.get('SHORTERNER_URL'),
            api_token=bot_config.get('URLSHORTX_API_TOKEN')
        )

        # 3. Create the link to your Flask app's gate
        # This will be the URL for the "🎟️ Get Token" button in Telegram
        request_id = str(uuid.uuid4())
        await save_shortener_link(request_id, external_shortened_url)

        flask_gate_link = f"{FLASK_APP_BASE_URL}/gate?id={request_id}"
        
        button1 = InlineKeyboardButton("🎟️ Get Token", url=flask_gate_link) # Link to your Flask app gate
        button2 = InlineKeyboardButton("How to get verified ✅", url=f'https://telegram.me/{bot_username}?start=token')
        button = InlineKeyboardMarkup([[button1], [button2]]) 
        return button
    except Exception as e:
        logger.error(f"error in update_token: {e}")
        return InlineKeyboardMarkup([[InlineKeyboardButton("Error getting token", callback_data="error_token")]])

async def genrate_token(user_id):
    try:
        token = str(uuid.uuid4())
        current_time = tm()
        new_data = {"token": token, "time": current_time, "status": "unverified", "file_count": 0, "inittime": current_time}
        await update_user_data(user_id, new_data)
        user_data[user_id] = {**user_data.get(user_id, {}), **new_data} # Update local cache
        
        bot_deep_link = f'https://telegram.dog/{bot_username}?start=token_{token}'
        external_shortened_url = await shorten_url(
            bot_deep_link,
            base_site=bot_config.get('SHORTERNER_URL'),
            api_token=bot_config.get('URLSHORTX_API_TOKEN')
        )

        request_id = str(uuid.uuid4())
        await save_shortener_link(request_id, external_shortened_url)

        flask_gate_link = f"{FLASK_APP_BASE_URL}/gate?id={request_id}"
        
        button1 = InlineKeyboardButton("🎟️ Get Token", url=flask_gate_link)
        button2 = InlineKeyboardButton("How to get verified ✅", url=f'https://telegram.me/{bot_username}?start=token')
        button = InlineKeyboardMarkup([[button1], [button2]]) 
        return button
    except Exception as e:
        logger.error(f"error in genrate_token: {e}")
        return InlineKeyboardMarkup([[InlineKeyboardButton("Error getting token", callback_data="error_token")]])

async def greet_user(message):
    user_link = await get_user_link(message.from_user)

    greeting_text = (
        f"Hello {user_link}, 👋\n\n"
        "Welcome to the official <b>TG⚡️FLIX Bot</b>! 🌟\n\n"
        "This is your personal delivery bot, where all your requested files will arrive.\n\n"
        "<b>How to get a file:</b>\n"
        "1. Browse our main channel.\n"
        "2. Tap the \"Send in DM\" button on any post.\n"
        "3. The file will be sent here!\n\n"
        "<b>Pro Tip:</b> You can always check your verification status and file limit by sending the <code>/me</code> command.\n\n"
        "Enjoy the show! 🎬"
    )

    rply = await message.reply_text(
        text=greeting_text,
        disable_web_page_preview=True
        )
    
    await auto_delete_message(message, rply)

async def get_user_link(user: User) -> str:
    try:
        user_id = user.id if hasattr(user, 'id') else None
        first_name = user.first_name if hasattr(user, 'first_name') else "Unknown"
    except Exception as e:
        logger.info(f"{e}")
        user_id = None
        first_name = "Unknown"
    
    if user_id:
        return f'<a href=tg://user?id={user_id}>{first_name}</a>'
    else:
        return first_name

async def daily_reset_scheduler():
    logging.info("Task started: daily_reset_scheduler")
    global user_data
    while True:
        try:
            # Run reset immediately on startup if needed
            if await reset_daily_stats_v2():
                await safe_api_call(lambda: bot.send_message(LOG_CHANNEL_ID, "✅ Daily statistics have been reset successfully."))

            sleep_duration = seconds_until_midnight_ist()
            logger.info(f"Daily reset scheduled to run in {sleep_duration:.0f} seconds.")
            await asyncio.sleep(sleep_duration)
        except Exception as e:
            logger.error(f"Error in daily_reset_scheduler: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute if error occurs

async def check_expired_tokens():
    logging.info("Task started: check_expired_tokens")
    global user_data
    while True:
        try:
            token_timeout = bot_config.get('TOKEN_TIMEOUT', TOKEN_TIMEOUT)
            expiry_threshold = tm() - token_timeout

            expired_users = await get_expired_users(expiry_threshold)

            if expired_users:
                logger.info(f"Found {len(expired_users)} expired tokens. Processing...")

                for user_id in expired_users:
                    # Update status in DB
                    await update_user_data(user_id, {'status': 'unverified'})

                    # Update local cache
                    if user_id in user_data:
                        user_data[user_id]['status'] = 'unverified'

                    # Notify user
                    logging.info(f"Attempting to notify user {user_id} of token expiry...")
                    try:
                        button = await update_token(user_id)
                        await safe_api_call(lambda: bot.send_message(
                            user_id,
                            "⚠️ <b>Token Expired</b>\n\nYour access has expired. Please get a new token to continue.",
                            reply_markup=button
                        ))
                        logging.info(f"Successfully notified user {user_id}.")
                    except UserIsBlocked:
                        logging.info(f"Could not notify user {user_id}: User has blocked the bot.")
                        pass # User blocked bot
                    except InputUserDeactivated:
                        logging.info(f"Could not notify user {user_id}: User account is deactivated.")
                        pass # User deleted account
                    except Exception as e:
                        logger.warning(f"Failed to notify user {user_id} about expiry: {e}")
                    
                    await asyncio.sleep(4) # Prevent FloodWait

        except Exception as e:
            logger.error(f"Error in token expiry check: {e}")

        # Check every 5 minutes
        await asyncio.sleep(300)

async def prune_inactive_users_scheduler():
    """A background task that runs once a day to prune inactive users."""
    while True:
        try:
            # Set the inactivity period to 40 days
            inactive_period_days = 40
            inactive_threshold = tm() - (inactive_period_days * 24 * 60 * 60)

            # Find and delete inactive users
            inactive_user_ids = await get_inactive_unverified_users(inactive_threshold)

            if inactive_user_ids:
                deleted_count = await delete_users_bulk(inactive_user_ids)

                # Log the result
                summary_message = f"✅ Automated Prune: Removed {deleted_count} inactive unverified users."
                logging.info(summary_message)
                await safe_api_call(lambda: bot.send_message(LOG_CHANNEL_ID, summary_message))
            else:
                logging.info("Automated Prune: No inactive users found to remove.")

        except Exception as e:
            error_message = f"Error in prune_inactive_users_scheduler: {e}"
            logging.error(error_message)
            await safe_api_call(lambda: bot.send_message(LOG_CHANNEL_ID, error_message))

        # Sleep for 24 hours before the next run
        await asyncio.sleep(24 * 60 * 60)

async def main():
    await load_initial_data()
    logging.info("Scheduling task: process_queue")
    asyncio.create_task(process_queue())
    logging.info("Scheduling task: daily_reset_scheduler")
    asyncio.create_task(daily_reset_scheduler())
    logging.info("Scheduling task: check_expired_tokens")
    asyncio.create_task(check_expired_tokens())
    logging.info("Scheduling task: prune_inactive_users_scheduler")
    asyncio.create_task(prune_inactive_users_scheduler())
    await asyncio.Event().wait()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    bot.send_message(LOG_CHANNEL_ID,"Bot Started ✅")
    
    try:
        # The bot is already started by Client(), so we just run the main loop
        bot.loop.run_until_complete(main())
        bot.loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
    finally:
        logger.info("Bot has stopped.")
