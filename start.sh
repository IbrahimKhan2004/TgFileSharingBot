#!/bin/bash
uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log & python3 bot.py