#!/bin/bash

IP="3.104.104.45"
KEY="./delta-bot-key.pem"
USER="ubuntu"

echo "[*] Connecting to live AWS Ichimoku Scalper dashboard..."
echo "(Press 'Ctrl+A' followed by 'D' to detach/disconnect without stopping the bot)"
echo "----------------------------------------------------"
sleep 2

ssh -i "$KEY" -t "$USER@$IP" "screen -r ichimoku-bot"
