#!/bin/bash
echo "==> Installing dependencies..."
pip install -r requirements.txt --break-system-packages
echo "==> Starting bot..."
python3 bot.py
