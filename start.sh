#!/bin/bash
echo "==> Installing dependencies..."
pip3 install python-telegram-bot==20.7 -q
echo "==> Starting bot..."
python3 bot.py
