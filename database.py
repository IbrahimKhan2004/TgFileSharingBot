import pymongo
from config import MONGO_URI, MONGO_DB_NAME
from time import time as tm
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo # ADDED: For robust timezone handling

dbclient = pymongo.MongoClient(MONGO_URI)
database = dbclient[MONGO_DB_NAME]

user_data = database['users']
banned_users = database['banned_users']
daily_stats = database['daily_stats']
shortener_requests = database['shortener_requests']
config_collection = database['config']

async def save_shortener_link(request_id: str, shortened_url: str):
    """Saves the shortened URL mapping."""
    # Ensure TTL index exists (expires after 1 hour)
    shortener_requests.create_index("created_at", expireAfterSeconds=3600)

    shortener_requests.insert_one({
        '_id': request_id,
        'shortened_url': shortened_url,
        'created_at': datetime.utcnow()
    })

def get_shortener_link_sync(request_id: str):
    """Gets the shortened URL (Synchronous for Flask)."""
    req = shortener_requests.find_one({'_id': request_id})
    return req.get('shortened_url') if req else None

async def present_user(user_id : int):
    found = user_data.find_one({'_id': user_id})
    return bool(found)

async def add_user(user_id: int):
    user_data.insert_one({
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
        user_data.update_one(
            {'_id': user_id},
            {'$set': update_doc},
            upsert=True
        )
    return

async def get_user_data(user_id: int):
    """Gets the user's data."""
    user = user_data.find_one({'_id': user_id})
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
    user_data.update_one(
        {'_id': user_id},
        {'$inc': {'file_count': 1}}
    )
    return

async def load_all_user_data():
    """Loads all user data from the database."""
    all_users = user_data.find({})
    all_user_data = {}
    for user in all_users:
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
    for doc in user_docs:
        user_ids.append(doc['_id'])
        
    return user_ids

async def del_user(user_id: int):
    user_data.delete_one({'_id': user_id})
    return

async def ban_user(user_id: int, ban_duration: int):
    """Bans a user for a specified duration (in seconds)."""
    ban_until = tm() + ban_duration
    banned_users.update_one(
        {'_id': user_id},
        {'$set': {'ban_until': ban_until}},
        upsert=True
    )
    return

async def unban_user(user_id: int):
    """Unbans a user."""
    banned_users.delete_one({'_id': user_id})
    await reset_bypass_attempts(user_id)
    return

async def get_bypass_attempts(user_id: int):
    """Gets the number of bypass attempts for a user."""
    user = user_data.find_one({'_id': user_id})
    return user.get('bypass_attempts', 0) if user else 0

async def increment_bypass_attempts(user_id: int):
    """Increments the bypass attempts for a user."""
    user_data.update_one(
        {'_id': user_id},
        {'$inc': {'bypass_attempts': 1}},
        upsert=True
    )
    return

async def reset_bypass_attempts(user_id: int):
    """Resets the bypass attempts for a user to 0."""
    user_data.update_one(
        {'_id': user_id},
        {'$set': {'bypass_attempts': 0}}
    )
    return

async def is_user_banned(user_id: int):
    """Checks if a user is currently banned."""
    user = banned_users.find_one({'_id': user_id})
    if user:
        ban_until = user.get('ban_until', 0)
        if tm() < ban_until:
            return True
        else:
            # Ban expired, remove from banned_users collection
            banned_users.delete_one({'_id': user_id})
            await reset_bypass_attempts(user_id)
            return False
    return False

async def daily_reset_stats():
    """Resets daily stats (file_count, status, time, inittime) for all users if a day has passed."""
    
    TZ_IST = ZoneInfo("Asia/Kolkata")
    stats_doc = daily_stats.find_one({'_id': 'daily_reset'})
    last_reset_timestamp = 0
    if stats_doc and isinstance(stats_doc.get('last_reset', 0), (int, float)):
        last_reset_timestamp = stats_doc.get('last_reset', 0)

    try:
        last_reset_date = datetime.fromtimestamp(last_reset_timestamp, tz=TZ_IST).date()
    except Exception:
        last_reset_date = datetime.now(TZ_IST).date() - timedelta(days=1)

    current_date = datetime.now(TZ_IST).date()

    if current_date != last_reset_date:
        user_data.update_many(
            {},
            {
                '$set': {
                    'file_count': 0,
                    'status': 'unverified',
                    'time': 0,
                    'bypass_attempts': 0,
                    'inittime': 0
                }
            }
        )
        daily_stats.update_one(
            {'_id': 'daily_reset'},
            {'$set': {'last_reset': tm()}},
            upsert=True
        )
        return True
    return False

async def get_dynamic_config():
    """Loads dynamic configuration from database."""
    config_doc = config_collection.find_one({'_id': 'bot_settings'})
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
    for doc in cursor:
        expired_user_ids.append(doc['_id'])
    return expired_user_ids

async def update_dynamic_config(key, value):
    """Updates a single configuration key."""
    config_collection.update_one(
        {'_id': 'bot_settings'},
        {'$set': {key: value}},
        upsert=True
    )
