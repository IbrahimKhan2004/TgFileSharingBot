import io
import re
import asyncio
from config import *
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, APIC
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot

def seconds_until_midnight_ist() -> float:
    """
    Returns the number of seconds until the next 12:00 am IST.
    """
    try:
        tz_ist = ZoneInfo("Asia/Kolkata")
    except Exception:
        tz_ist = timezone.utc

    now = datetime.now(tz_ist)
    tomorrow = now.date() + timedelta(days=1)
    midnight = datetime.combine(tomorrow, time(0, 0, 0), tzinfo=tz_ist)
    return (midnight - now).total_seconds()

async def remove_unwanted(input_string):
    # Use regex to match .mkv or .mp4 and everything that follows
    result = re.split(r'(\.mkv|\.mp4)', input_string)
    # Join the first two parts to get the string up to the extension
    return ''.join(result[:2])

async def remove_extension(caption):
    try:
        # Remove .mkv and .mp4 extensions if present
        cleaned_caption = re.sub(r'\.mkv|\.mp4|\.webm', '', caption)
        return cleaned_caption
    except Exception as e:
        logger.error(e)
        return None
    
async def auto_delete_message(user_message, bot_message, delay=60):
    try:
        if user_message:
            await user_message.delete()
        await asyncio.sleep(delay)
        await bot_message.delete()
    except Exception as e:
        logger.error(f"{e}")

async def extract_tg_link(telegram_link):
    try:
        # Pattern for private channel links (t.me/c/channel_id/message_id)
        private_pattern = re.compile(r'https://t\.me/c/(-?\d+)/(\d+)')
        private_match = private_pattern.match(telegram_link)
        if private_match:
            message_id = private_match.group(2)
            return message_id

        # Pattern for public channel links (t.me/channel_username/message_id)
        public_pattern = re.compile(r'https://t\.me/([a-zA-Z0-9_]+)/(\d+)')
        public_match = public_pattern.match(telegram_link)
        if public_match:
            message_id = public_match.group(2)
            return message_id

        return None # No match found for either pattern
    except Exception as e:
        logger.error(e)
        return None

def humanbytes(size):
    # Function to format file size in a human-readable format
    if not size:
        return "0 B"
    # Define byte sizes
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    i = 0
    while size >= 1024 and i < len(suffixes) - 1:
        size /= 1024
        i += 1
    f = ('%.2f' % size).rstrip('0').rstrip('.')
    return f"{f} {suffixes[i]}"

async def extract_movie_info(caption):
    try:
        regex = re.compile(r'(.+?)(\d{4})')
        match = regex.search(caption)

        if match:
            # Replace '.' and remove '(' and ')' from movie_name
            movie_name = match.group(1).replace('.', ' ').replace('(', '').replace(')', '').strip()
            release_year = match.group(2)
            return movie_name, release_year
    except Exception as e:
        print(e)
    return None, None


def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + " days, ") if days else "") + \
        ((str(hours) + " hrs, ") if hours else "") + \
        ((str(minutes) + " min, ") if minutes else "") + \
        ((str(seconds) + " sec, ") if seconds else "") + \
        ((str(milliseconds) + " millisec, ") if milliseconds else "")
    return tmp[:-2]

def get_readable_time(seconds: int) -> str:
    result = ""
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f"{days}d"
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f"{hours}h"
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f" {minutes}m"
    seconds = int(seconds)
    result += f" {seconds}s"
    return result

async def get_audio_thumbnail(audio_path):
    audio = MutagenFile(audio_path)
    if isinstance(audio, MP3):
        if audio.tags and isinstance(audio.tags, ID3):
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    return io.BytesIO(tag.data)
    elif isinstance(audio, FLAC):
        if audio.pictures:
            return io.BytesIO(audio.pictures[0].data)
    elif isinstance(audio, MP4):
        if audio.tags and 'covr' in audio.tags:
            cover = audio.tags['covr'][0]
            return io.BytesIO(cover)
    return None

async def safe_api_call(coro_factory, max_retries=3):
    """Utility wrapper to add delay and retry for flood waits."""
    retries = 0
    while retries < max_retries:
        try:
            return await coro_factory()
        except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot) as e:
            raise e
        except FloodWait as e:
            retries += 1
            if retries < max_retries:
                sleep_duration = e.value * 1.2
                logger.warning(f"FloodWait: Sleeping for {sleep_duration:.2f} seconds before retrying. Attempt {retries}/{max_retries}")
                await asyncio.sleep(sleep_duration)
            else:
                logger.error(f"FloodWait limit reached after {max_retries} attempts. Giving up. {e}")
                return None
        except Exception as e:
            logger.error(f"An error occurred during an API call: {e}")
            return None
    return None
