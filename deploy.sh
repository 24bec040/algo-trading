#!/bin/bash

# AWS Deployment Script for Trade Bot
echo "[*] Starting AWS Setup..."

# 1. Update System
sudo apt update -y
sudo apt upgrade -y

# 2. Install Dependencies
echo "[*] Installing Python and Screen..."
sudo apt install python3-pip screen -y

# 3. Install Python Packages
echo "[*] Installing Bot Requirements..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
else
    pip3 install requests rich numpy
fi

echo ""
echo "===================================================="
echo "    SETUP COMPLETE! YOUR BOT IS READY FOR CLOUD     "
echo "===================================================="
echo ""
echo "To run the bot 24/7 (even when you close your Mac):"
echo "1. Type:  screen -S bot"
echo "2. Type:  python3 bot.py"
echo "3. Press: Ctrl+A then D  (to detach)"
echo ""
echo "To check the bot later:"
echo "1. Type:  screen -r bot"
echo "===================================================="
