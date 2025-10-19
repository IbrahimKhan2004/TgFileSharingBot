import pymongo
from config import MONGO_URI, MONGO_DB_NAME
from time import time as tm

dbclient = pymongo.MongoClient(MONGO_URI)
database = dbclient[MONGO_DB_NAME]

user_data = database['users']
banned_users = database['banned_users']

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
