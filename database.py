import pymongo
import uuid
from config import MONGO_URI, MONGO_DB_NAME
from time import time as tm

dbclient = pymongo.MongoClient(MONGO_URI)
database = dbclient[MONGO_DB_NAME]

# Collections
users_collection = database['users']
banned_users_collection = database['banned_users']
tickets_collection = database['tickets']
user_data_collection = database['user_data']

# --- User Presence ---

async def present_user(user_id: int):
    return bool(users_collection.find_one({'_id': user_id}))

async def add_user(user_id: int):
    users_collection.insert_one({'_id': user_id})
    return

async def full_userbase():
    user_docs = users_collection.find()
    return [doc['_id'] for doc in user_docs]

async def del_user(user_id: int):
    users_collection.delete_one({'_id': user_id})
    user_data_collection.delete_one({'_id': user_id}) # Also delete their session data
    return

# --- Banning ---

async def ban_user(user_id: int, ban_duration: int):
    """Bans a user for a specified duration (in seconds)."""
    ban_until = tm() + ban_duration
    banned_users_collection.update_one(
        {'_id': user_id},
        {'$set': {'ban_until': ban_until}},
        upsert=True
    )
    return

async def is_user_banned(user_id: int):
    """Checks if a user is currently banned."""
    user = banned_users_collection.find_one({'_id': user_id})
    if user and tm() < user.get('ban_until', 0):
        return True
    elif user:
        # Ban expired, remove from banned_users collection
        banned_users_collection.delete_one({'_id': user_id})
        return False
    return False

# --- Verification Tickets (for Captcha flow) ---

async def create_ticket(user_id: int, user_token: str) -> str:
    """Creates a new verification ticket and stores it in the database."""
    ticket_id = str(uuid.uuid4())
    ticket_data = {
        '_id': ticket_id,
        'user_id': user_id,
        'user_token': user_token, # The final token the user will get
        'created_at': tm()
    }
    tickets_collection.insert_one(ticket_data)
    return ticket_id

async def get_ticket(ticket_id: str):
    """Retrieves a ticket from the database."""
    # Tickets older than 10 minutes are considered expired
    ten_minutes_ago = tm() - 600
    return tickets_collection.find_one({'_id': ticket_id, 'created_at': {'$gte': ten_minutes_ago}})

def get_ticket_sync(ticket_id: str):
    """Synchronous version of get_ticket for Flask app."""
    ten_minutes_ago = tm() - 600
    return tickets_collection.find_one({'_id': ticket_id, 'created_at': {'$gte': ten_minutes_ago}})

async def delete_ticket(ticket_id: str):
    """Deletes a used or expired ticket from the database."""
    tickets_collection.delete_one({'_id': ticket_id})
    return

def delete_ticket_sync(ticket_id: str):
    """Synchronous version of delete_ticket for Flask app."""
    tickets_collection.delete_one({'_id': ticket_id})
    return

# --- Persistent User Data (for token, status, etc.) ---

async def update_user_data(user_id: int, data: dict):
    """Creates or updates a user's session data in the database."""
    user_data_collection.update_one(
        {'_id': user_id},
        {'$set': data},
        upsert=True
    )
    return

async def get_user_data(user_id: int):
    """Retrieves a user's session data from the database."""
    return user_data_collection.find_one({'_id': user_id})
