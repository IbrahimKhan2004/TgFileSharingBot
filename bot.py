import uvloop
import asyncio
import uuid
import sys
from time import time as tm
from pyrogram.types import User
from pyrogram import Client, enums, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, WebpageCurlFailed, WebpageMediaEmpty
from asyncio import Queue
from config import *
from utils import *
from tmdb import get_by_name
from shorterner import shorten_url
from database import (
    add_user, del_user, full_userbase, present_user,
    ban_user, is_user_banned, create_ticket,
    update_user_data, get_user_data
)
import urllib.parse

# uvloop.install() # This is causing a conflict with gunicorn

# Define an async queue to handle messages sequentially
message_queue = Queue()

# PROGRAM BOT INITIALIZATION
bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=1000,
    parse_mode=enums.ParseMode.HTML
)

@bot.on_message(filters.private & filters.command("start"))
async def start_command(client, message):
    try:
        user_id = message.from_user.id

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
            
            # Handle tutorial flow
            if command_arg == "token":
                msg = await safe_api_call(bot.get_messages(LOG_CHANNEL_ID, TUT_ID))
                sent_msg = await safe_api_call(msg.copy(chat_id=message.chat.id))
                await safe_api_call(message.delete())
                await asyncio.sleep(300)
                await safe_api_call(sent_msg.delete())
                return

            # Handle token verification
            if command_arg.startswith("token_"):
                input_token = command_arg[6:]
                
                # Bypass detection logic
                current_user_data = await get_user_data(user_id)
                if current_user_data and 'inittime' in current_user_data:
                    inittime = current_user_data['inittime']
                    duration = tm() - inittime
                    if MINIMUM_DURATION and (duration < MINIMUM_DURATION):
                        await ban_user(user_id, 86400) # Ban for 1 day
                        
                        # Reset user data in DB
                        await update_user_data(user_id, {
                            'status': "unverified",
                            'time': 0,
                            'file_count': 0
                        })
                        
                        log_message = (
                            f"User🕵️‍♂️{user_link} with 🆔 {user_id} @{bot.me.username} "
                            f"attempted token bypass! ❌ **BANNED for 1 Day**\n"
                            f"Time taken: {duration:.2f} seconds (Min required: {MINIMUM_DURATION} seconds)\n"
                            f"Token: `{input_token}`"
                        )
                        await safe_api_call(bot.send_message(LOG_CHANNEL_ID, log_message, parse_mode=enums.ParseMode.HTML))
                        
                        warning_message = (
                            f"**Bypass Detected! 🚨**\n\n"
                            f"You have been **BANNED for 1 Day** for attempting to bypass the system."
                        )
                        reply = await safe_api_call(message.reply_text(warning_message))
                        await auto_delete_message(message, reply)
                        return
                
                token_msg = await verify_token(user_id, input_token)
                reply = await safe_api_call(message.reply_text(token_msg))
                await safe_api_call(bot.send_message(LOG_CHANNEL_ID, f"User🕵️‍♂️{user_link} with 🆔 {user_id} @{bot.me.username} {token_msg}", parse_mode=enums.ParseMode.HTML))
                await auto_delete_message(message, reply)
                return

            # Handle file flow
            file_id = int(command_arg)
            can_access, access_message = await check_access(user_id)
            if not can_access:
                button = await generate_token_button(user_id)
                send_message = await message.reply_text(text=access_message, reply_markup=button)
                await auto_delete_message(message, send_message)
                return

            file_message = await safe_api_call(bot.get_messages(DB_CHANNEL_ID, file_id))
            media = file_message.video or file_message.audio or file_message.document
            if media:
                caption = await remove_extension(file_message.caption.html or "")
                copy_message = await safe_api_call(file_message.copy(chat_id=message.chat.id, caption=f"<b>{caption}</b>", parse_mode=enums.ParseMode.HTML))

                # Increment file count in DB
                user_db_data = await get_user_data(user_id)
                new_file_count = user_db_data.get('file_count', 0) + 1
                await update_user_data(user_id, {'file_count': new_file_count})

                await auto_delete_message(message, copy_message)
            else:
                await auto_delete_message(message, await message.reply_text("File not found or inaccessible."))
            return

        # Default flow (no arguments)
        await greet_user(message)
        
    except ValueError:
        reply = await safe_api_call(message.reply_text("Invalid File ID."))
        await auto_delete_message(message, reply)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await auto_delete_message(message, await message.reply_text(f"An error occurred: {e}"))

async def verify_token(user_id, input_token):
    """Verifies a token against the one stored in the database."""
    user_db_data = await get_user_data(user_id)

    if not user_db_data or 'token' not in user_db_data:
        return 'Token Mismatched ❌'

    if input_token == user_db_data['token']:
        new_token = str(uuid.uuid4())
        current_time = tm()

        await update_user_data(user_id, {
            "token": new_token,
            "time": current_time,
            "status": "verified",
            "file_count": 0,
            "inittime": current_time
        })
        return f'Token Verified ✅ (Validity: {get_readable_time(TOKEN_TIMEOUT)})'
    else:
        return 'Token Mismatched ❌'

async def check_access(user_id):
    """Checks user access from the database. Returns (bool, message)."""
    user_db_data = await get_user_data(user_id)

    if not user_db_data or 'status' not in user_db_data:
        return False, "👋 Welcome! Please get a token to access files. 🚀"

    status = user_db_data.get('status', 'unverified')

    if status != "verified":
        return False, "Your token is not verified. Please get a new token. 🚀"

    time = user_db_data.get('time', 0)
    expiry = time + TOKEN_TIMEOUT

    if tm() >= expiry:
        return False, "Your token has expired. Please get a new one. 🚀"

    file_count = user_db_data.get('file_count', 0)
    if file_count >= DAILY_LIMIT:
        return False, f"You have reached your daily limit of {DAILY_LIMIT} files."

    return True, "Access granted."

async def generate_token_button(user_id):
    """Generates the secure 'Get Token' button."""
    try:
        user_token = str(uuid.uuid4())
        current_time = tm()

        # Store the token and initial time in the DB before the user clicks the link
        await update_user_data(user_id, {
            "token": user_token,
            "time": current_time,
            "status": "unverified",
            "file_count": 0,
            "inittime": current_time
        })

        ticket_id = await create_ticket(user_id, user_token)

        # This is the new, secure URL for the captcha page
        captcha_url = f"{FLASK_APP_BASE_URL}/verify?ticket={ticket_id}"

        button1 = InlineKeyboardButton("🎟️ Get Token", url=captcha_url)
        button2 = InlineKeyboardButton("How to get verified ✅", url=f'https://telegram.me/{bot.me.username}?start=token')
        return InlineKeyboardMarkup([[button1], [button2]])

    except Exception as e:
        logger.error(f"Error in generate_token_button: {e}")
        return InlineKeyboardMarkup([[InlineKeyboardButton("Error getting token", callback_data="error_token")]])

# --- Unchanged Functions Below ---

@bot.on_message(filters.chat(DB_CHANNEL_ID) & (filters.document | filters.video |filters.audio | filters.sticker))
async def handle_new_message(client, message):
    await message_queue.put(message)
    
@bot.on_message(filters.private & filters.command("index") & filters.user(OWNER_ID))
async def handle_file(client, message):
    try:
        async def get_user_input(prompt):
            bot_message = await message.reply_text(prompt)
            user_message = await bot.listen(chat_id=message.chat.id, filters=filters.user(OWNER_ID))
            asyncio.create_task(auto_delete_message(bot_message, user_message))
            return await extract_tg_link(user_message.text.strip())

        start_msg_id = int(await get_user_input("Send first msg link"))
        end_msg_id = int(await get_user_input("Send end msg link"))

        for i in range(start_msg_id, end_msg_id + 1):
            try:
                file_message = await bot.get_messages(DB_CHANNEL_ID, i)
                await message_queue.put(file_message)
            except Exception:
                pass # Ignore if message not found
        await message.reply_text("Done indexing!")
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

@bot.on_message(filters.private & filters.command("delete") & filters.user(OWNER_ID))
async def delete_messages_command(client, message):
    try:
        async def get_user_input(prompt):
            bot_message = await message.reply_text(prompt)
            user_message = await bot.listen(chat_id=message.chat.id, filters=filters.user(OWNER_ID))
            asyncio.create_task(auto_delete_message(bot_message, user_message))
            return await extract_tg_link(user_message.text.strip())

        start_msg_id = int(await get_user_input("Send start message link from UPDATE_CHANNEL_ID:"))
        end_msg_id = int(await get_user_input("Send end message link from UPDATE_CHANNEL_ID:"))

        message_ids = [i for i in range(start_msg_id, end_msg_id + 1)]
        await client.delete_messages(chat_id=UPDATE_CHANNEL_ID, message_ids=message_ids)
        await message.reply_text(f"Successfully deleted {len(message_ids)} messages.")
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")

@bot.on_message(filters.private & filters.command('broadcast') & filters.user(OWNER_ID))
async def send_text(client, message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total, successful, blocked, deleted, unsuccessful = 0, 0, 0, 0, 0
        
        pls_wait = await message.reply("<i>Broadcasting...</i>")
        for chat_id in query:
            try:
                await asyncio.sleep(1) # Reduced sleep
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except (UserIsBlocked, InputUserDeactivated):
                await del_user(chat_id)
                if isinstance(e, UserIsBlocked): blocked += 1
                else: deleted += 1
            except Exception:
                unsuccessful += 1
            total += 1
        
        status = f"<b>Broadcast Completed</b>\nTotal: {total}, Successful: {successful}, Blocked: {blocked}, Deleted: {deleted}, Unsuccessful: {unsuccessful}"
        await pls_wait.edit(status)
    else:
        await message.reply("Reply to a message to broadcast it.")

@bot.on_message(filters.command('users') & filters.private & filters.user(OWNER_ID))
async def get_users(client, message):
    msg = await client.send_message(chat_id=message.chat.id, text="Counting users...")
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@bot.on_message(filters.command("log") & filters.user(OWNER_ID))
async def log_command(client, message):
    try:
        await bot.send_document(message.chat.id, document=LOG_FILE_NAME, caption="Bot Log File")
    except Exception as e:
        await bot.send_message(message.chat.id, f"Failed to send log file. Error: {str(e)}")

async def process_queue():
    while True:
        message = await message_queue.get()
        await process_message(bot, message)
        message_queue.task_done()

async def process_message(client, message):
    media = message.document or message.video or message.audio
    if media:
        caption = message.caption or media.file_name
        file_name = await remove_extension(caption)
        file_size = humanbytes(media.file_size)
        duration = TimeFormatter(media.duration * 1000) if message.video else ""

        info = f"<blockquote expandable><b>{file_name}</b></blockquote>\n<blockquote><b>{file_size}</b> {duration}</blockquote>"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Send in DM", url=f"https://telegram.dog/{bot.me.username}?start={message.id}")]])

        poster_url = None
        thumbnail = None
        if message.video and media.thumbs:
            thumbnail = await safe_api_call(bot.download_media(media.thumbs[0].file_id))
        elif not message.audio:
            movie_name, release_year = await extract_movie_info(file_name)
            poster_url = await get_by_name(movie_name, release_year)

        try:
            photo_to_send = poster_url or thumbnail
            if photo_to_send:
                await safe_api_call(bot.send_photo(UPDATE_CHANNEL_ID, photo=photo_to_send, caption=info, reply_markup=keyboard))
            else:
                await safe_api_call(bot.send_message(UPDATE_CHANNEL_ID, text=info, reply_markup=keyboard))
            if thumbnail: os.remove(thumbnail)
        except (WebpageMediaEmpty, WebpageCurlFailed):
            await safe_api_call(bot.send_message(UPDATE_CHANNEL_ID, text=info, reply_markup=keyboard))
        except FloodWait as f:
            await asyncio.sleep(f.value)
            await process_message(client, message)
        except Exception as e:
            await safe_api_call(bot.send_message(OWNER_ID, text=f"Error Processing MSG: {file_name}\nError: {e}"))
    elif message.sticker:
        await safe_api_call(message.copy(UPDATE_CHANNEL_ID))

@bot.on_message(filters.command('restart') & filters.private & filters.user(OWNER_ID))
async def restart(client, message):
    os.system("python3 update.py")
    os.execl(sys.executable, sys.executable, *sys.argv)

async def greet_user(message):
    user_link = await get_user_link(message.from_user)
    greeting_text = f"Hello {user_link}, 👋\n\nWelcome to FileShare Bot! 🌟"
    rply = await message.reply_text(text=greeting_text)
    await auto_delete_message(message, rply)

async def get_user_link(user: User) -> str:
    return f'<a href=tg://user?id={user.id}>{user.first_name}</a>'

async def main():
    await bot.start()
    asyncio.create_task(process_queue())
    await bot.send_message(LOG_CHANNEL_ID, "Bot Started ✅")
    await asyncio.Event().wait()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        logger.info("Bot stopped.")
