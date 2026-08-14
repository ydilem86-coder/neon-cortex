#!/bin/bash
# NEON Cortex Bot - Quick Deploy Script
# Usage: bash deploy.sh

echo "========================================="
echo "  NEON Cortex Bot - Deploy"
echo "========================================="

# Update system
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt install python3-pip python3-venv ffmpeg git -y

# Clone or copy project
echo "[3/6] Setting up project..."
if [ ! -d "discord-bot" ]; then
    echo "Upload your project files to /home/ubuntu/discord-bot/"
    echo "Or run: git clone https://github.com/your-repo/discord-bot.git"
    exit 1
fi

cd discord-bot

# Create virtual environment
echo "[4/6] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "[5/6] Installing Python packages..."
pip install -r requirements.txt -r web/requirements.txt

# Start bot
echo "[6/6] Starting bot..."
cd web
nohup python3 run_web.py 8000 > bot.log 2>&1 &

echo ""
echo "========================================="
echo "  Bot is running!"
echo "  Open: http://YOUR_IP:8000"
echo "========================================="
