import uvloop
import asyncio
import uuid
import sys
from time import time as tm
from asyncio import create_subprocess_exec, gather
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
    ban_user, is_user_banned, unban_user,
    get_bypass_attempts, increment_bypass_attempts,
    update_user_data, get_user_data, increment_file_count, load_all_user_data
)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Define an async queue to handle messages sequentially
message_queue = Queue()

user_data = {}

# PROGRAM BOT INITIALIZATION 

async def load_initial_data():
    global user_data
    user_data = await load_all_user_data()
    logger.info("Successfully loaded all user data from the database.")

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
                if user_id in user_data and 'inittime' in user_data[user_id]:
                    inittime = user_data[user_id]['inittime']
                    duration = tm() - inittime
                    if MINIMUM_DURATION and (duration < MINIMUM_DURATION):
                        await increment_bypass_attempts(user_id)
                        attempts = await get_bypass_attempts(user_id)

                        ban_duration = 0
                        ban_message = ""

                        if attempts == 1:
                            # 1st bypass: Warning
                            warning_message = (
                                f"**First Warning! ⚠️**\n\n"
                                f"This is your first warning for attempting to bypass the verification process. "
                                f"Please follow the proper steps. Further attempts will result in a ban."
                            )
                            reply = await safe_api_call(message.reply_text(warning_message))
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
                            f"attempted token bypass! ❌ **{ban_message}** (Attempt: {attempts})\n"
                            f"Time taken: {duration:.2f} seconds (Min required: {MINIMUM_DURATION} seconds)\n"
                            f"Token: `{input_token}`"
                        )
                        await safe_api_call(bot.send_message(LOG_CHANNEL_ID, log_message, parse_mode=enums.ParseMode.HTML))
                        
                        warning_message = (
                            f"**Bypass Detected! 🚨**\n\n"
                            f"You have been **{ban_message}** for repeatedly attempting to bypass the verification process. "
                            f"Your token has been invalidated."
                        )
                        reply = await safe_api_call(message.reply_text(warning_message))
                        await auto_delete_message(message, reply)
                        return
                
                token_msg = await verify_token(user_id, input_token)
                reply = await safe_api_call(message.reply_text(token_msg))
                await safe_api_call(bot.send_message(LOG_CHANNEL_ID, f"User🕵️‍♂️{user_link} with 🆔 {user_id} @{bot_username} {token_msg}", parse_mode=enums.ParseMode.HTML))
                await auto_delete_message(message, reply)
                return

            # Handle file flow
            file_id = int(command_arg)
            if not await check_access(message, user_id):
                return

            file_message = await safe_api_call(bot.get_messages(DB_CHANNEL_ID, file_id))
            media = file_message.video or file_message.audio or file_message.document
            if media:
                caption = await remove_extension(file_message.caption.html or "")
                copy_message = await safe_api_call(file_message.copy(chat_id=message.chat.id, caption=f"<b>{caption}</b>", parse_mode=enums.ParseMode.HTML))
                await increment_file_count(user_id)
                user_data[user_id]['file_count'] += 1
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


@bot.on_message(filters.chat(DB_CHANNEL_ID) & (filters.document | filters.video |filters.audio | filters.sticker))
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
                    await safe_api_call(client.delete_messages(chat_id=UPDATE_CHANNEL_ID, message_ids=messages_to_delete))
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
        for chat_id in query:
            try:
                await asyncio.sleep(3)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply("<code>Use this command as a replay to any telegram message with out any spaces.</code>")
        await asyncio.sleep(8)
        await msg.delete()

@bot.on_message(filters.command('users') & filters.private & filters.user(OWNER_ID))
async def get_users(client, message):
    msg = await client.send_message(chat_id=message.chat.id, text="Please Wait..")
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@bot.on_message(filters.command('stats') & filters.private & filters.user(OWNER_ID))
async def get_stats(client, message):
    msg = await client.send_message(chat_id=message.chat.id, text="Gathering statistics...")

    # Get total users from the database
    users = await full_userbase()
    total_users = len(users)

    # Calculate current verified users from local cache (approximation)
    verified_users = sum(1 for data in user_data.values() if data.get('status') == 'verified')
    
    # Calculate total files shared today (since last bot start and token refresh)
    files_shared = sum(data.get('file_count', 0) for data in user_data.values())

    stats_text = (
        "📊 <b>BOT STATISTICS</b> 📊\n\n"
        f"<b>Total Users:</b> <code>{total_users}</code>\n"
        f"<b>Verified Users (Active):</b> <code>{verified_users}</code>\n"
        f"<b>Total Files Shared:</b> <code>{files_shared}</code>\n"
        f"<b>Token Timeout:</b> <code>{get_readable_time(TOKEN_TIMEOUT)}</code>\n"
        f"<b>Daily File Limit:</b> <code>{DAILY_LIMIT}</code> files"
    )

    await msg.edit(stats_text)

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

async def process_queue():
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
            thumbnail = await safe_api_call(bot.download_media(media.thumbs[0].file_id))
        else:
            duration = ""
        if not message.audio: 
            movie_name, release_year = await extract_movie_info(file_name)
            poster_url = await get_by_name(movie_name, release_year)
        if message.audio:
            audio_path = await safe_api_call(bot.download_media(message.audio.file_id))
            audio_thumb = await get_audio_thumbnail(audio_path)

        file_id = message.id
        v_info = f"<blockquote expandable><b>{file_name}</b></blockquote>\n<blockquote><b>{file_size}</b></blockquote>\n<blockquote><b>{duration}</b></blockquote>"
        if message.audio:
            a_info = f"<blockquote ><b>{media.title}</b></blockquote>\n<blockquote><b>{media.performer}</b></blockquote>"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Send in DM", url=f"https://telegram.dog/{bot_username}?start={file_id}")]])

        try:           
            if poster_url:
                await safe_api_call(bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=poster_url,
                    caption=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                    ))
            elif thumbnail:
                await safe_api_call(bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=thumbnail,
                    caption=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                ))
            elif not message.audio:
                await safe_api_call(bot.send_message(
                    UPDATE_CHANNEL_ID,
                    text=v_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard 
                    ))
                
            if message.audio:
                await safe_api_call(bot.send_photo(
                    UPDATE_CHANNEL_ID,
                    photo=audio_thumb,
                    caption=a_info,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=keyboard
                    ))
                os.remove(audio_path) 

        except (WebpageMediaEmpty, WebpageCurlFailed):
            logger.info(f"{poster_url}")
            await safe_api_call(bot.send_message(
                UPDATE_CHANNEL_ID,
                text=v_info,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=keyboard
                ))

        except FloodWait as f:
            await asyncio.sleep(f.value)
            await process_message(client, message)

        except Exception as e:
            await safe_api_call(bot.send_message(OWNER_ID, text=f"Error in Proccessing MSG:{file_name} {e}"))
    
    elif message.sticker:
        await safe_api_call(message.copy(UPDATE_CHANNEL_ID))


@bot.on_message(filters.command('restart') & filters.private & filters.user(OWNER_ID))
async def restart(client, message):
    os.system("python3 update.py")  
    os.execl(sys.executable, sys.executable, "bot.py")

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
        user_data[user_id] = {**udata, **new_data} # Update local cache
        return f'Token Verified ✅ (Validity: {get_readable_time(TOKEN_TIMEOUT)})'
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

    expiry = time + TOKEN_TIMEOUT
    current_time = tm()

    if current_time < expiry and status == "verified":
        if file_count < DAILY_LIMIT:
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
        external_shortened_url = await shorten_url(bot_deep_link)

        # 3. Create the link to your Flask app's gate
        # This will be the URL for the "🎟️ Get Token" button in Telegram
        flask_gate_link = (
            f"{FLASK_APP_BASE_URL}/gate?"
            f"redirect_to_shortener={urllib.parse.quote_plus(external_shortened_url)}" # Pass the URL shortener link to Flask
        )
        
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
        external_shortened_url = await shorten_url(bot_deep_link)

        flask_gate_link = (
            f"{FLASK_APP_BASE_URL}/gate?"
            f"redirect_to_shortener={urllib.parse.quote_plus(external_shortened_url)}"
        )
        
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
        "Welcome to FileShare Bot! 🌟\n\n"
        "Here, you can easily access files.\n"
        "<b>○ Creator : <b>TG⚡️FLIX</b>"
        "\n<b>○ Language : Python</b>"
    )

    rply = await message.reply_text(
        text=greeting_text
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

async def main():
    await load_initial_data()
    await asyncio.create_task(process_queue())
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
