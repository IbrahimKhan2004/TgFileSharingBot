import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# 1. Mock environment variables for config.py
os.environ['API_ID'] = '12345'
os.environ['API_HASH'] = 'abcde'
os.environ['BOT_TOKEN'] = '123:abc'
os.environ['OWNER_ID'] = '123'
os.environ['DB_CHANNEL_ID'] = '123'
os.environ['LOG_CHANNEL_ID'] = '123'
os.environ['UPDATE_CHANNEL_ID'] = '123'
os.environ['TUT_ID'] = '123'
os.environ['DAILY_LIMIT'] = '10'
os.environ['TOKEN_TIMEOUT'] = '3600'
os.environ['MONGO_URI'] = 'mongodb://localhost'
os.environ['TMDB_API_KEY'] = 'test'
os.environ['URLSHORTX_API_TOKEN'] = 'test'
os.environ['SHORTERNER_URL'] = 'test.com'

# 2. Mock heavy modules
import pyrogram
mock_pyrogram = MagicMock()
sys.modules['pyrogram'] = mock_pyrogram
sys.modules['pyrogram.types'] = MagicMock()

# Mock specific exceptions to allow them to be used in 'except' clauses
class MockPyrogramError(Exception): pass
class UserIsBlocked(MockPyrogramError): pass
class InputUserDeactivated(MockPyrogramError): pass
class PeerIdInvalid(MockPyrogramError): pass
class UserIsBot(MockPyrogramError): pass
class FloodWait(MockPyrogramError):
    def __init__(self, value=10):
        self.value = value
        self.x = value

mock_errors = MagicMock()
mock_errors.UserIsBlocked = UserIsBlocked
mock_errors.InputUserDeactivated = InputUserDeactivated
mock_errors.PeerIdInvalid = PeerIdInvalid
mock_errors.UserIsBot = UserIsBot
mock_errors.FloodWait = FloodWait
sys.modules['pyrogram.errors'] = mock_errors

sys.modules['pyrogram.enums'] = MagicMock()
sys.modules['motor'] = MagicMock()
sys.modules['motor.motor_asyncio'] = MagicMock()
sys.modules['pymongo'] = MagicMock()
# sys.modules['uvloop'] = MagicMock() # Let it use the installed one or mock properly

# Mock bot instance in bot.py to prevent .start()
with patch('pyrogram.Client') as MockClient:
    instance = MockClient.return_value
    instance.start.return_value = instance
    import bot
    import utils

class TestBotQueueLogic(unittest.IsolatedAsyncioTestCase):

    async def test_process_queue_exception_handling(self):
        """
        Tests that process_queue continues to run even if process_message raises an exception.
        """
        mock_message = MagicMock()
        mock_message.id = 999

        # We want to mock message_queue.get to return one message then None (to break loop)
        with patch('bot.message_queue.get', side_effect=[mock_message, None]), \
             patch('bot.process_message', new_callable=AsyncMock) as mock_process, \
             patch('bot.logger.error') as mock_log_error, \
             patch('bot.message_queue.task_done') as mock_task_done, \
             patch('asyncio.sleep', new_callable=AsyncMock):

            # Set process_message to raise an error
            mock_process.side_effect = Exception("Simulated processing error")

            # Run the queue
            await bot.process_queue()

            # Assertions
            mock_process.assert_called_once()
            mock_log_error.assert_called_once()
            # Ensure task_done was called despite the error
            mock_task_done.assert_called_once()

    async def test_safe_api_call_suppression(self):
        """
        Tests that safe_api_call catches and logs exceptions without raising them.
        """
        mock_coro = AsyncMock(side_effect=Exception("Telegram Delete Forbidden"))

        with patch('utils.logger.error') as mock_log_error:
            result = await utils.safe_api_call(mock_coro)

            self.assertIsNone(result)
            mock_log_error.assert_called_once()
            # Check if the error message contains our simulated error
            args, kwargs = mock_log_error.call_args
            self.assertIn("Telegram Delete Forbidden", args[0])

if __name__ == '__main__':
    unittest.main()
