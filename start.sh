#!/bin/bash

echo "--- Starting Bot Process ---"
python3 bot.py > bot.log 2>&1 &

echo "--- Waiting for Bot to Initialize (5s) ---"
sleep 5

echo "--- Starting Web Process ---"
gunicorn app:app --workers 1 --threads 1 --bind 0.0.0.0:${PORT:-8080} --timeout 86400
