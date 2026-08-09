#!/bin/bash

IP="3.104.104.45"
KEY="./delta-bot-key.pem"
USER="ubuntu"

echo "===================================================="
echo "          STARTING ICHIMOKU SERVICE ON AWS          "
echo "===================================================="

ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "sudo systemctl start ichimoku-bot.service"

echo "[✔] SYSTEMD SERVICE LAUNCHED! Ichimoku Bot is running."
echo "----------------------------------------------------"
echo "To monitor the Ichimoku dashboard, run:"
echo "  ./view_ichimoku_on_aws.sh"
echo "===================================================="
