#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  RPOW3 Miner + Telegram Bot — VPS Auto-Installer
#  Run:  bash install.sh
# ═══════════════════════════════════════════════════════════════

set -e

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   RPOW3 MINER + TELEGRAM BOT INSTALLER      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 1. Update system & install Python
echo "→ Updating system packages..."
sudo apt update -y && sudo apt upgrade -y

echo "→ Installing Python 3, pip, git, screen..."
sudo apt install -y python3 python3-pip python3-venv git screen

# 2. Clone your repo (user will replace URL)
REPO_DIR="$HOME/rpow3-tg-miner"

if [ -d "$REPO_DIR" ]; then
    echo "→ Directory already exists. Pulling latest..."
    cd "$REPO_DIR"
    git pull || true
else
    echo ""
    echo "→ Cloning repo..."
    # REPLACE THIS URL WITH YOUR GITHUB REPO URL
    git clone https://github.com/YOUR_USERNAME/rpow3-tg-miner.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# 3. Create virtual environment
echo "→ Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 4. Install dependencies
echo "→ Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Run the bot (setup wizard will ask questions)
echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅  Installation complete!"
echo ""
echo "  Now run:  cd $REPO_DIR && source venv/bin/activate && python3 bot.py"
echo ""
echo "  Or to run in background with screen:"
echo "    screen -S miner"
echo "    cd $REPO_DIR && source venv/bin/activate && python3 bot.py"
echo "    (press Ctrl+A then D to detach)"
echo "═══════════════════════════════════════════════"
