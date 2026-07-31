#!/bin/bash

IP="3.104.104.45"
KEY="/Users/chandu/Downloads/delta-bot-key.pem"
USER="ubuntu"

echo "===================================================="
echo "          STOPPING BOT SERVICE ON AWS               "
echo "===================================================="

ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "sudo systemctl stop delta-bot.service"

echo "[✔] SYSTEMD SERVICE STOPPED. Bot is offline."
echo "===================================================="
