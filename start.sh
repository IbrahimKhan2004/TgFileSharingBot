#!/bin/bash

# Start the bot in the background
python3 bot.py &

# Start the Gunicorn web server in the foreground
gunicorn app:app --workers 1 --threads 1 --bind 0.0.0.0:${PORT:-8080} --timeout 86400
