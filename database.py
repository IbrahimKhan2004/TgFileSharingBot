import pymongo
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, MONGO_DB_NAME
from time import time as tm
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Async Client for Bot (Pyrogram) and Flask App (Asynchronous) - Using Motor
async_client = AsyncIOMotorClient(MONGO_URI)
async_db = async_client[MONGO_DB_NAME]

# Collections for Async use
user_data = async_db['users']
banned_users = async_db['banned_users']
daily_stats = async_db['daily_stats']
shortener_requests = async_db['shortener_requests']
config_collection = async_db['config']

async def ensure_ttl_index():
    """
    Ensures the TTL index on 'shortener_requests' collection is correctly set to 24 hours.
    This function will automatically drop a conflicting index if it exists.
    """
    index_name = "created_at_1"
    new_ttl = 86400  # 24 hours

    try:
        # Get existing index information
        existing_indexes = await shortener_requests.index_information()
        if index_name in existing_indexes:
            existing_ttl = existing_indexes[index_name].get('expireAfterSeconds')
            # If the TTL is different, drop the old index
            if existing_ttl != new_ttl:
                await shortener_requests.drop_index(index_name)

        # Create the new index
        await shortener_requests.create_index("created_at", expireAfterSeconds=new_ttl, name=index_name)
    except Exception as e:
        # This might fail if another process is creating it at the same time, which is fine.
        # The important part is handling the conflict.
        pass

async def save_shortener_link(request_id: str, shortened_url: str):
    """Saves the shortened URL mapping."""
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
    found = await user_data.find_one({'_id': user_id})
    return bool(found)

async def add_user(user_id: int):
    await user_data.insert_one({
        '_id': user_id,
        'bypass_attempts': 0,
        'token': None,
        'time': 0,
        'status': 'unverified',
        'file_count': 0,
        'inittime': 0
    })
    return

async def update_user_data(user_id: int, data: dict):
    """Updates the user's data document."""
    valid_fields = ['token', 'time', 'status', 'file_count', 'inittime', 'bypass_attempts']
    update_doc = {k: v for k, v in data.items() if k in valid_fields}
    if update_doc:
        await user_data.update_one(
            {'_id': user_id},
            {'$set': update_doc},
            upsert=True
        )
    return

async def get_user_data(user_id: int):
    """Gets the user's data."""
    user = await user_data.find_one({'_id': user_id})
    if user:
        return {
            'token': user.get('token'),
            'time': user.get('time', 0),
            'status': user.get('status', 'unverified'),
            'file_count': user.get('file_count', 0),
            'inittime': user.get('inittime', 0),
            'bypass_attempts': user.get('bypass_attempts', 0)
        }
    return None

async def increment_file_count(user_id: int):
    """Increments the file count for a user."""
    await user_data.update_one(
        {'_id': user_id},
        {'$inc': {'file_count': 1}}
    )
    return

async def load_all_user_data():
    """Loads all user data from the database."""
    # Motor's find() returns an AsyncIOMotorCursor which is an async iterable
    all_users = user_data.find({})
    all_user_data = {}
    async for user in all_users:
        all_user_data[user['_id']] = {
            'token': user.get('token'),
            'time': user.get('time', 0),
            'status': user.get('status', 'unverified'),
            'file_count': user.get('file_count', 0),
            'inittime': user.get('inittime', 0),
            'bypass_attempts': user.get('bypass_attempts', 0)
        }
    return all_user_data

async def full_userbase():
    user_docs = user_data.find()
    user_ids = []
    async for doc in user_docs:
        user_ids.append(doc['_id'])
        
    return user_ids

async def del_user(user_id: int):
    await user_data.delete_one({'_id': user_id})
    return

async def ban_user(user_id: int, ban_duration: int):
    """Bans a user for a specified duration (in seconds)."""
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
    """Gets the number of bypass attempts for a user."""
    user = await user_data.find_one({'_id': user_id})
    return user.get('bypass_attempts', 0) if user else 0

async def increment_bypass_attempts(user_id: int):
    """Increments the bypass attempts for a user."""
    await user_data.update_one(
        {'_id': user_id},
        {'$inc': {'bypass_attempts': 1}},
        upsert=True
    )
    return

async def reset_bypass_attempts(user_id: int):
    """Resets the bypass attempts for a user to 0."""
    await user_data.update_one(
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
            # Ban expired, remove from banned_users collection
            await banned_users.delete_one({'_id': user_id})
            await reset_bypass_attempts(user_id)
            return False
    return False

# --- New Daily Statistics Functions ---

STATS_ID = "daily_stats_v2" # Single document ID for daily stats

async def get_daily_stats():
    """Retrieves the daily statistics document."""
    stats = await daily_stats.find_one({'_id': STATS_ID})
    if not stats:
        # Initialize if it doesn't exist
        return {'verified_today': 0, 'files_shared_today': 0}
    return stats

async def increment_verified_today():
    """Increments the count of users verified today."""
    await daily_stats.update_one(
        {'_id': STATS_ID},
        {'$inc': {'verified_today': 1}},
        upsert=True
    )

async def increment_files_shared_today():
    """Increments the count of files shared today."""
    await daily_stats.update_one(
        {'_id': STATS_ID},
        {'$inc': {'files_shared_today': 1}},
        upsert=True
    )

# --- End New Daily Statistics Functions ---

async def reset_daily_stats_v2():
    """Resets only the daily statistics counters."""
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
        # Handle cases where last_reset is not a valid timestamp or doesn't exist
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
        # Exclude _id from the returned dictionary
        return {k: v for k, v in config_doc.items() if k != '_id'}
    return {}

async def get_expired_users(expiry_threshold):
    """
    Returns a list of user IDs whose status is 'verified' and
    token creation time is less than the expiry_threshold.
    """
    query = {
        'status': 'verified',
        'time': {'$lt': expiry_threshold}
    }
    # Return only _id field
    cursor = user_data.find(query, {'_id': 1})
    expired_user_ids = []
    async for doc in cursor:
        expired_user_ids.append(doc['_id'])
    return expired_user_ids

async def update_dynamic_config(key, value):
    """Updates a single configuration key."""
    await config_collection.update_one(
        {'_id': 'bot_settings'},
        {'$set': {key: value}},
        upsert=True
    )

async def get_inactive_unverified_users(inactive_threshold):
    """
    Returns a list of user IDs for users who are 'unverified' and whose
    'inittime' is older than the inactive_threshold.
    """
    query = {
        'status': 'unverified',
        'inittime': {'$lt': inactive_threshold}
    }
    cursor = user_data.find(query, {'_id': 1})
    inactive_user_ids = [doc['_id'] async for doc in cursor]
    return inactive_user_ids

async def delete_users_bulk(user_ids):
    """Deletes a list of users from the database in bulk."""
    if not user_ids:
        return 0
    result = await user_data.delete_many({'_id': {'$in': user_ids}})
    return result.deleted_count
