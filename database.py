import pymongo
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, MONGO_URI_2, MONGO_DB_NAME
from time import time as tm
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

# Async Client for Bot (Pyrogram) and Flask App (Asynchronous) - Using Motor
async_client = AsyncIOMotorClient(MONGO_URI)
async_db = async_client[MONGO_DB_NAME]

# Collections for Async use (DB 1)
user_data = async_db['users']
banned_users = async_db['banned_users']
daily_stats = async_db['daily_stats']
shortener_requests = async_db['shortener_requests']
config_collection = async_db['config']
processed_files = async_db['processed_files']

# Initialize Second Database if URI is present
async_client_2 = None
async_db_2 = None
user_data_2 = None
processed_files_2 = None

if MONGO_URI_2:
    try:
        async_client_2 = AsyncIOMotorClient(MONGO_URI_2)
        async_db_2 = async_client_2[MONGO_DB_NAME]
        user_data_2 = async_db_2['users']
        processed_files_2 = async_db_2['processed_files']
        logger.info("Connected to Secondary Database (DB 2) successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to Secondary Database: {e}")
        async_client_2 = None


async def add_processed_file(file_unique_id, caption, content_hash=None, hash_middle=None, hash_end=None, file_size=None, file_name=None, duration=None):
    """
    Adds a file's metadata and hashes to the processed files collection.
    Tries DB1 first; if it fails (e.g. quota full), tries DB2.
    """
    document = {
        '_id': file_unique_id,
        'caption': caption,
        'processed_at': tm()
    }
    if content_hash: document['content_hash'] = content_hash
    if hash_middle: document['hash_middle'] = hash_middle
    if hash_end: document['hash_end'] = hash_end
    if file_size: document['file_size'] = file_size
    if file_name: document['file_name'] = file_name
    if duration: document['duration'] = duration

    # Try inserting into DB 1
    try:
        await processed_files.insert_one(document)
        return # Success
    except pymongo.errors.DuplicateKeyError:
        return # Already exists, ignore
    except pymongo.errors.WriteError as e:
        logger.warning(f"WriteError on DB 1 (likely full): {e}. Attempting DB 2...")
    except Exception as e:
        logger.warning(f"Unexpected error on DB 1: {e}. Attempting DB 2...")

    # Fallback to DB 2 if available
    if processed_files_2 is not None:
        try:
            await processed_files_2.insert_one(document)
            logger.info(f"Saved file {file_unique_id} to DB 2.")
        except pymongo.errors.DuplicateKeyError:
            pass
        except Exception as e:
            logger.error(f"Failed to save file to DB 2 as well: {e}")
    else:
        logger.error("DB 2 not configured or unavailable. File save failed.")

async def is_file_processed(file_unique_id, caption, content_hash=None, file_size=None, file_name=None, duration=None):
    """
    Checks if a file is a duplicate.
    Checks DB1 first, then DB2 if not found.
    Returns the matching document if found, otherwise None.
    """
    query_conditions = [
        {'_id': file_unique_id},
        {'caption': caption}
    ]

    if content_hash:
        query_conditions.append({'content_hash': content_hash})

    # Composite check for re-uploads with different IDs/Hashes
    if file_size and file_name:
        query_conditions.append({
            'file_size': file_size,
            'file_name': file_name,
            'duration': duration
        })

    query = {'$or': query_conditions}

    # Check DB 1
    result = await processed_files.find_one(query)
    if result:
        return result

    # Check DB 2 (if available)
    if processed_files_2 is not None:
        result_2 = await processed_files_2.find_one(query)
        if result_2:
            return result_2

    return None

async def remove_processed_file_by_caption(caption: str):
    """Removes a file's record from processed files collection(s) based on its caption."""
    deleted_count = 0
    # Delete from DB 1
    res1 = await processed_files.delete_one({'caption': caption})
    deleted_count += res1.deleted_count

    # Delete from DB 2
    if processed_files_2 is not None:
        res2 = await processed_files_2.delete_one({'caption': caption})
        deleted_count += res2.deleted_count

    return deleted_count

async def remove_processed_file_by_id_or_hash(file_unique_id: str, content_hash: str = None):
    """Removes a file's record based on file_unique_id or content_hash."""
    or_conditions = [{'_id': file_unique_id}]
    if content_hash:
        or_conditions.append({'content_hash': content_hash})

    query = {'$or': or_conditions}

    deleted_count = 0
    # Delete from DB 1
    res1 = await processed_files.delete_many(query)
    deleted_count += res1.deleted_count

    # Delete from DB 2
    if processed_files_2 is not None:
        res2 = await processed_files_2.delete_many(query)
        deleted_count += res2.deleted_count

    return deleted_count

async def remove_any_duplicate(arg: str):
    """Removes a record matching the argument by _id, hashes, or caption."""
    query = {
        '$or': [
            {'_id': arg},
            {'content_hash': arg},
            {'hash_middle': arg},
            {'hash_end': arg},
            {'file_name': arg},
            {'caption': arg}
        ]
    }

    deleted_count = 0
    # Delete from DB 1
    res1 = await processed_files.delete_many(query)
    deleted_count += res1.deleted_count

    # Delete from DB 2
    if processed_files_2 is not None:
        res2 = await processed_files_2.delete_many(query)
        deleted_count += res2.deleted_count

    return deleted_count

async def ensure_indexes():
    """Ensures necessary indexes are created on startup (on both DBs)."""
    # Helper for creating indexes on a collection
    async def create_idxs(collection):
        await collection.create_index([("caption", pymongo.ASCENDING)])
        await collection.create_index([("content_hash", pymongo.ASCENDING)], sparse=True)
        await collection.create_index([("hash_middle", pymongo.ASCENDING)], sparse=True)
        await collection.create_index([("hash_end", pymongo.ASCENDING)], sparse=True)
        await collection.create_index([("file_name", pymongo.ASCENDING)], sparse=True)
        await collection.create_index([
            ("file_name", pymongo.ASCENDING),
            ("file_size", pymongo.ASCENDING),
            ("duration", pymongo.ASCENDING)
        ], sparse=True)

    await create_idxs(processed_files)
    if processed_files_2 is not None:
        await create_idxs(processed_files_2)

async def save_shortener_link(request_id: str, shortened_url: str):
    """Saves the shortened URL mapping. (Only needs to be in DB1 for now)"""
    try:
        await shortener_requests.create_index("created_at", expireAfterSeconds=86400)
    except Exception as e:
        if "IndexOptionsConflict" in str(e):
             await shortener_requests.drop_index("created_at_1")
             await shortener_requests.create_index("created_at", expireAfterSeconds=86400)
        else:
            raise e

    await shortener_requests.insert_one({
        '_id': request_id,
        'shortened_url': shortened_url,
        'created_at': datetime.utcnow()
    })

async def get_shortener_link_async(request_id: str):
    """Gets the shortened URL (Asynchronous for Flask)."""
    req = await shortener_requests.find_one({'_id': request_id})
    return req.get('shortened_url') if req else None

async def present_user(user_id : int):
    # Check DB 1
    found = await user_data.find_one({'_id': user_id})
    if found: return True

    # Check DB 2
    if user_data_2 is not None:
        found_2 = await user_data_2.find_one({'_id': user_id})
        return bool(found_2)

    return False

async def add_user(user_id: int):
    """Adds a new user. Tries DB1 first, then DB2."""
    user_doc = {
        '_id': user_id,
        'bypass_attempts': 0,
        'token': None,
        'time': 0,
        'status': 'unverified',
        'file_count': 0,
        'extension_stage': 0,
        'inittime': 0
    }

    try:
        await user_data.insert_one(user_doc)
        return
    except pymongo.errors.WriteError:
        pass # Try DB 2
    except Exception:
        pass

    if user_data_2 is not None:
        try:
            await user_data_2.insert_one(user_doc)
        except:
            pass
    return

async def update_user_data(user_id: int, data: dict):
    """Updates the user's data document. checks where user exists and updates there."""
    # Added user_channel_id and user_channel_name to valid fields
    valid_fields = ['token', 'time', 'status', 'file_count', 'extension_stage', 'inittime', 'bypass_attempts', 'user_channel_id', 'user_channel_name']

    # Handle $unset operations if passed in data (keys starting with $)
    # If data contains MongoDB operators (like $unset), pass them directly
    if any(k.startswith('$') for k in data.keys()):
        # Try Update DB 1
        res = await user_data.update_one({'_id': user_id}, data)

        # If not found in DB 1, try DB 2
        if res.matched_count == 0 and user_data_2 is not None:
             await user_data_2.update_one({'_id': user_id}, data)
        return

    update_doc = {k: v for k, v in data.items() if k in valid_fields}
    if not update_doc: return

    # Try Update DB 1
    res = await user_data.update_one(
        {'_id': user_id},
        {'$set': update_doc}
    )

    # If not found in DB 1, try DB 2
    if res.matched_count == 0 and user_data_2 is not None:
        await user_data_2.update_one(
            {'_id': user_id},
            {'$set': update_doc},
            upsert=True # If user moved to DB2 or new
        )
    elif res.matched_count == 0 and user_data_2 is None:
        # If DB2 not active, upsert to DB1
         await user_data.update_one(
            {'_id': user_id},
            {'$set': update_doc},
            upsert=True
        )
    return

async def get_user_data(user_id: int):
    """Gets the user's data. Checks both DBs."""
    user = await user_data.find_one({'_id': user_id})
    if not user and user_data_2 is not None:
        user = await user_data_2.find_one({'_id': user_id})

    if user:
        return {
            'token': user.get('token'),
            'time': user.get('time', 0),
            'status': user.get('status', 'unverified'),
            'file_count': user.get('file_count', 0),
            'extension_stage': user.get('extension_stage', 0),
            'inittime': user.get('inittime', 0),
            'bypass_attempts': user.get('bypass_attempts', 0),
            'user_channel_id': user.get('user_channel_id'),
            'user_channel_name': user.get('user_channel_name')
        }
    return None

async def increment_file_count(user_id: int):
    """Increments the file count for a user."""
    res = await user_data.update_one(
        {'_id': user_id},
        {'$inc': {'file_count': 1}}
    )
    if res.matched_count == 0 and user_data_2 is not None:
        await user_data_2.update_one(
            {'_id': user_id},
            {'$inc': {'file_count': 1}}
        )
    return

async def load_all_user_data():
    """Loads all user data from both databases."""
    all_user_data = {}

    # Load from DB 1
    async for user in user_data.find({}):
        all_user_data[user['_id']] = {
            'token': user.get('token'),
            'time': user.get('time', 0),
            'status': user.get('status', 'unverified'),
            'file_count': user.get('file_count', 0),
            'extension_stage': user.get('extension_stage', 0),
            'inittime': user.get('inittime', 0),
            'bypass_attempts': user.get('bypass_attempts', 0)
        }

    # Load from DB 2 (Overwrites if duplicate ID, which shouldn't happen ideally)
    if user_data_2 is not None:
        async for user in user_data_2.find({}):
            all_user_data[user['_id']] = {
                'token': user.get('token'),
                'time': user.get('time', 0),
                'status': user.get('status', 'unverified'),
                'file_count': user.get('file_count', 0),
                'extension_stage': user.get('extension_stage', 0),
                'inittime': user.get('inittime', 0),
                'bypass_attempts': user.get('bypass_attempts', 0)
            }

    return all_user_data

async def full_userbase():
    user_ids = []
    async for doc in user_data.find():
        user_ids.append(doc['_id'])
        
    if user_data_2 is not None:
        async for doc in user_data_2.find():
            if doc['_id'] not in user_ids:
                user_ids.append(doc['_id'])

    return user_ids

async def del_user(user_id: int):
    await user_data.delete_one({'_id': user_id})
    if user_data_2 is not None:
        await user_data_2.delete_one({'_id': user_id})
    return

async def ban_user(user_id: int, ban_duration: int):
    """Bans a user. Stores ban info in DB1 usually."""
    ban_until = tm() + ban_duration
    await banned_users.update_one(
        {'_id': user_id},
        {'$set': {'ban_until': ban_until}},
        upsert=True
    )
    return

async def unban_user(user_id: int):
    """Unbans a user."""
    await banned_users.delete_one({'_id': user_id})
    await reset_bypass_attempts(user_id)
    return

async def get_bypass_attempts(user_id: int):
    """Gets the number of bypass attempts."""
    user = await get_user_data(user_id) # Reuse get_user_data to check both DBs
    return user.get('bypass_attempts', 0) if user else 0

async def increment_bypass_attempts(user_id: int):
    """Increments the bypass attempts."""
    res = await user_data.update_one(
        {'_id': user_id},
        {'$inc': {'bypass_attempts': 1}}
    )
    if res.matched_count == 0 and user_data_2 is not None:
         await user_data_2.update_one(
            {'_id': user_id},
            {'$inc': {'bypass_attempts': 1}}
        )
    return

async def reset_bypass_attempts(user_id: int):
    """Resets the bypass attempts."""
    res = await user_data.update_one(
        {'_id': user_id},
        {'$set': {'bypass_attempts': 0}}
    )
    if res.matched_count == 0 and user_data_2 is not None:
        await user_data_2.update_one(
            {'_id': user_id},
            {'$set': {'bypass_attempts': 0}}
        )
    return

async def is_user_banned(user_id: int):
    """Checks if a user is currently banned."""
    user = await banned_users.find_one({'_id': user_id})
    if user:
        ban_until = user.get('ban_until', 0)
        if tm() < ban_until:
            return True
        else:
            await banned_users.delete_one({'_id': user_id})
            await reset_bypass_attempts(user_id)
            return False
    return False

# --- New Daily Statistics Functions ---

STATS_ID = "daily_stats_v2"

async def get_daily_stats():
    """Retrieves the daily statistics document (DB1)."""
    stats = await daily_stats.find_one({'_id': STATS_ID})
    if not stats:
        return {'verified_today': 0, 'files_shared_today': 0}
    return stats

async def increment_verified_today():
    await daily_stats.update_one(
        {'_id': STATS_ID},
        {'$inc': {'verified_today': 1}},
        upsert=True
    )

async def increment_files_shared_today():
    await daily_stats.update_one(
        {'_id': STATS_ID},
        {'$inc': {'files_shared_today': 1}},
        upsert=True
    )

# --- End New Daily Statistics Functions ---

async def reset_daily_stats_v2():
    try:
        TZ_IST = ZoneInfo("Asia/Kolkata")
    except Exception:
        TZ_IST = timezone.utc

    stats_doc = await daily_stats.find_one({'_id': STATS_ID})

    last_reset_timestamp = 0
    if stats_doc and 'last_reset' in stats_doc:
        last_reset_timestamp = stats_doc['last_reset']

    try:
        last_reset_date = datetime.fromtimestamp(last_reset_timestamp, tz=TZ_IST).date()
    except (TypeError, ValueError):
        last_reset_date = datetime.now(TZ_IST).date() - timedelta(days=1)

    current_date = datetime.now(TZ_IST).date()

    if current_date != last_reset_date:
        await daily_stats.update_one(
            {'_id': STATS_ID},
            {
                '$set': {
                    'verified_today': 0,
                    'files_shared_today': 0,
                    'last_reset': tm()
                }
            },
            upsert=True
        )
        return True
    return False

async def get_dynamic_config():
    """Loads dynamic configuration from database."""
    config_doc = await config_collection.find_one({'_id': 'bot_settings'})
    if config_doc:
        return {k: v for k, v in config_doc.items() if k != '_id'}
    return {}

async def get_expired_users(expiry_threshold):
    """Returns a list of user IDs from both DBs."""
    query = {
        'status': 'verified',
        'time': {'$lt': expiry_threshold}
    }
    expired_user_ids = []

    # DB 1
    async for doc in user_data.find(query, {'_id': 1}):
        expired_user_ids.append(doc['_id'])

    # DB 2
    if user_data_2 is not None:
        async for doc in user_data_2.find(query, {'_id': 1}):
            if doc['_id'] not in expired_user_ids:
                expired_user_ids.append(doc['_id'])

    return expired_user_ids

async def update_dynamic_config(key, value):
    await config_collection.update_one(
        {'_id': 'bot_settings'},
        {'$set': {key: value}},
        upsert=True
    )

async def get_inactive_unverified_users(inactive_threshold):
    """Returns a list of user IDs from both DBs."""
    query = {
        'status': 'unverified',
        'inittime': {'$lt': inactive_threshold}
    }
    inactive_user_ids = []

    async for doc in user_data.find(query, {'_id': 1}):
        inactive_user_ids.append(doc['_id'])

    if user_data_2 is not None:
        async for doc in user_data_2.find(query, {'_id': 1}):
            if doc['_id'] not in inactive_user_ids:
                inactive_user_ids.append(doc['_id'])

    return inactive_user_ids

async def delete_users_bulk(user_ids):
    if not user_ids: return 0
    deleted = 0

    res1 = await user_data.delete_many({'_id': {'$in': user_ids}})
    deleted += res1.deleted_count

    if user_data_2 is not None:
        res2 = await user_data_2.delete_many({'_id': {'$in': user_ids}})
        deleted += res2.deleted_count

    return deleted

# --- New Admin Functions: Stats & Clean ---

def humanbytes(size):
    if not size: return "0 B"
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

async def get_db_stats():
    """Returns storage usage statistics for both databases."""
    stats_text = "📊 <b>DB Stats:</b>\n\n"

    try:
        db1_stats = await async_db.command("dbStats")
        data_size = humanbytes(db1_stats.get('dataSize'))
        storage_size = humanbytes(db1_stats.get('storageSize'))
        stats_text += f"<b>DB 1:</b>\nData: {data_size}\nStorage: {storage_size}\n\n"
    except Exception as e:
        stats_text += f"<b>DB 1:</b> Error fetching stats: {e}\n\n"

    if async_db_2 is not None:
        try:
            db2_stats = await async_db_2.command("dbStats")
            data_size = humanbytes(db2_stats.get('dataSize'))
            storage_size = humanbytes(db2_stats.get('storageSize'))
            stats_text += f"<b>DB 2:</b>\nData: {data_size}\nStorage: {storage_size}\n"
        except Exception as e:
            stats_text += f"<b>DB 2:</b> Error fetching stats: {e}\n"
    else:
        stats_text += "<b>DB 2:</b> Not Connected (No URI)"

    return stats_text

async def clean_db(target: str):
    """
    Cleans the database based on target: 'files', 'users', or 'all'.
    Executes on BOTH databases if available.
    """
    target = target.lower().strip()
    msg = ""

    # Clean Files
    if target == 'files' or target == 'all':
        try:
            r1 = await processed_files.delete_many({})
            count = r1.deleted_count
            if processed_files_2 is not None:
                r2 = await processed_files_2.delete_many({})
                count += r2.deleted_count
            msg += f"✅ Removed {count} processed file records.\n"
        except Exception as e:
            msg += f"❌ Error cleaning files: {e}\n"

    # Clean Users
    if target == 'users' or target == 'all':
        try:
            r1 = await user_data.delete_many({})
            count = r1.deleted_count
            if user_data_2 is not None:
                r2 = await user_data_2.delete_many({})
                count += r2.deleted_count
            msg += f"✅ Removed {count} user records.\n"
        except Exception as e:
            msg += f"❌ Error cleaning users: {e}\n"

    if not msg:
        msg = "⚠️ Invalid target. Use 'files', 'users', or 'all'."

    return msg
