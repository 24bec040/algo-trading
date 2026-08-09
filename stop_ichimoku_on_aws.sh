#!/bin/bash

IP="3.104.104.45"
KEY="./delta-bot-key.pem"
USER="ubuntu"

echo "===================================================="
echo "          STOPPING ICHIMOKU SERVICE ON AWS          "
echo "===================================================="

ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "sudo systemctl stop ichimoku-bot.service"

echo "[✔] SYSTEMD SERVICE STOPPED. Ichimoku Bot is offline."
echo "===================================================="
