#!/bin/bash

# AWS Deployment Script
IP="3.104.104.45"
KEY="./delta-bot-key.pem"
USER="ubuntu"

echo "===================================================="
echo "          STARTING DEPLOYMENT TO AWS                "
echo "===================================================="

# 1. Set key permission
echo "[*] Setting secure permissions for pem key..."
chmod 400 "$KEY"

# 2. Test Connection
echo "[*] Testing connection to AWS server..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "echo 'Connected Successfully!'"
if [ $? -ne 0 ]; then
    echo "[!] ERROR: Cannot connect to AWS. Check if server is running and security block allows SSH."
    exit 1
fi

# 3. Create destination folder
echo "[*] Creating folder structure on AWS..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "mkdir -p ~/trade-bot"

# 4. Copy files
echo "[*] Copying bot files to AWS..."
scp -i "$KEY" -o StrictHostKeyChecking=no delta_client.py logger.py ichimoku_bot.py ichimoku_config.py ichimoku-bot.service requirements.txt deploy.sh "$USER@$IP:~/trade-bot/"
if [ $? -ne 0 ]; then
    echo "[!] ERROR: Failed to transfer files."
    exit 1
fi

# 5. Run setup script remotely
echo "[*] Launching installer on the cloud server (this takes about 1-2 minutes)..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$USER@$IP" "chmod +x ~/trade-bot/deploy.sh && cd ~/trade-bot && ./deploy.sh"

echo "===================================================="
echo "          DEPLOYMENT COMPLETED SUCCESSFULLY         "
echo "===================================================="
