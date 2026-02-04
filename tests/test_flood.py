import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os
import time

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

# Mock bot instance in bot.py to prevent .start()
with patch('pyrogram.Client') as MockClient:
    instance = MockClient.return_value
    instance.start.return_value = instance
    import bot
    import utils

class TestFloodWaitLogic(unittest.IsolatedAsyncioTestCase):

    async def test_process_queue_timings(self):
        """
        Tests that process_queue respects the 10-second sleep interval.
        """
        mock_message = MagicMock()
        mock_message.id = 1

        with patch('bot.message_queue', new_callable=MagicMock) as mock_queue, \
             patch('bot.process_message', new_callable=AsyncMock) as mock_process, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            # Setup the queue.get to return message then None
            mock_queue.get = AsyncMock(side_effect=[mock_message, None])

            # Execute
            await bot.process_queue()

            # Verify:
            # 1. process_message called once
            mock_process.assert_called_once()
            # 2. sleep(10) called once (in the finally block)
            mock_sleep.assert_called_with(10)
            # 3. task_done called
            mock_queue.task_done.assert_called_once()

    async def test_process_message_hash_timings(self):
        """
        Tests that process_message sleeps 10s between hash chunks.
        """
        mock_message = MagicMock()
        mock_message.document = MagicMock()
        mock_message.document.file_unique_id = "unique_id"
        mock_message.document.file_size = 10 * 1024 * 1024 # 10MB
        mock_message.video = None
        mock_message.audio = None
        mock_message.caption = "Test File"

        async def mock_stream_generator(*args, **kwargs):
            yield b"chunk_data"

        with patch('bot.bot.stream_media', side_effect=mock_stream_generator) as mock_stream, \
             patch('bot.is_file_processed', new_callable=AsyncMock) as mock_is_processed, \
             patch('bot.add_processed_file', new_callable=AsyncMock), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
             patch('bot.remove_extension', new_callable=AsyncMock), \
             patch('bot.extract_movie_info', new_callable=AsyncMock) as mock_extract, \
             patch('bot.get_by_name', new_callable=AsyncMock), \
             patch('bot.safe_api_call', new_callable=AsyncMock):

            mock_is_processed.return_value = None
            mock_extract.return_value = ("Movie Name", "2024")

            await bot.process_message(bot.bot, mock_message)

            # Assertions
            calls = [call.args[0] for call in mock_sleep.call_args_list if call.args[0] == 10]
            self.assertEqual(len(calls), 2, "Should sleep 10s twice during hash computation for > 2MB file")

    async def test_flood_wait_handling(self):
        """
        Tests that if Telegram raises FloodWait(45), the bot waits 45+5 = 50 seconds.
        """
        mock_message = MagicMock()
        mock_message.document = MagicMock()
        mock_message.document.file_unique_id = "unique_id"
        mock_message.document.file_size = 5 * 1024 * 1024
        mock_message.video = None
        mock_message.audio = None
        mock_message.caption = "Test File Flood"

        # Simulate: First call raises FloodWait(45), Second call succeeds
        async def mock_stream_fail_then_success(*args, **kwargs):
             # First attempt raises FloodWait
             if mock_stream_fail_then_success.counter == 0:
                 mock_stream_fail_then_success.counter += 1
                 raise FloodWait(45) # Telegram says wait 45s
             # Second attempt yields data
             yield b"chunk_data"

        mock_stream_fail_then_success.counter = 0

        with patch('bot.bot.stream_media', side_effect=mock_stream_fail_then_success) as mock_stream, \
             patch('bot.is_file_processed', new_callable=AsyncMock) as mock_is_processed, \
             patch('bot.add_processed_file', new_callable=AsyncMock), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep, \
             patch('bot.remove_extension', new_callable=AsyncMock), \
             patch('bot.extract_movie_info', new_callable=AsyncMock) as mock_extract, \
             patch('bot.get_by_name', new_callable=AsyncMock), \
             patch('bot.safe_api_call', new_callable=AsyncMock):

            mock_is_processed.return_value = None
            mock_extract.return_value = ("Movie Name", "2024")

            await bot.process_message(bot.bot, mock_message)

            # Assert that sleep(50) was called (45 + 5 buffer)
            # The exact logic in bot.py is: wait_time = e.value + 5 -> await asyncio.sleep(wait_time)

            mock_sleep.assert_any_call(50)

if __name__ == '__main__':
    unittest.main()
