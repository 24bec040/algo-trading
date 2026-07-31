#!/bin/bash

IP="3.104.104.45"
KEY="/Users/chandu/Downloads/delta-bot-key.pem"
USER="ubuntu"

echo "===================================================="
echo "          STARTING BOT SERVICE ON AWS               "
echo "===================================================="

ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "sudo systemctl start delta-bot.service"

echo "[✔] SYSTEMD SERVICE LAUNCHED! Bot is running 24/7."
echo "----------------------------------------------------"
echo "To monitor the bot dashboard, run:"
echo "  ./view_bot_on_aws.sh"
echo "===================================================="
