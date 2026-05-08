# ⛏ RPOW3 Miner — Telegram Bot (One-Click Setup)

Mine RPOW3 tokens from the command line and control everything via Telegram.  
**No Node.js. No separate miner repo. Just one Python file.**

---

## What This Does

This script:
1. **Asks you a few questions** when you first run it (bot token, email, workers)
2. **Logs you into rpow3.com** via magic-link email
3. **Mines tokens** using pure Python SHA-256 proof-of-work (multi-process)
4. **Sends live updates** to your Telegram bot
5. **Lets you control everything** from Telegram buttons — start, stop, status, send tokens, etc.

---

## 🚀 Quick Start (Copy-Paste)

### Step 1: Get a Telegram Bot Token

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Follow prompts → copy the **bot token** it gives you

### Step 2: Install & Run

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/rpow3-tg-miner.git
cd rpow3-tg-miner

# Install dependencies
pip install -r requirements.txt

# Run — it will ask you questions interactively
python3 bot.py
```

### Step 3: Answer the Setup Questions

```
╔══════════════════════════════════════════════╗
║    RPOW3 MINER + TELEGRAM BOT  —  SETUP     ║
╚══════════════════════════════════════════════╝

  STEP 1: Paste your BOT TOKEN here: 123456:ABC-DEF...
  STEP 2: Your Telegram user ID: 987654321
  STEP 3: Your email: you@example.com
  STEP 4: Workers [4]: 4
  STEP 5: Tokens to mine per /mine command [1]: 1

  ✅  Config saved to config.json

══════════════════════════════════════════════════
  🚀  Bot is running!  Open Telegram and send /start
══════════════════════════════════════════════════
```

### Step 4: Open Telegram

Send `/start` to your bot. You'll see buttons for everything:

```
⛏ Start Mining    🛑 Stop
📊 Status          💰 Balance
📜 Activity        📒 Ledger
🔑 Login           🚪 Logout
💸 Send            📝 Logs
ℹ️ Help
```

---

## 🔑 First-Time Login

Before mining, you need to log in:

```
/login you@email.com        ← sends magic link to your inbox
/complete_login https://...  ← paste the link from your email
```

After that, your session is saved — you won't need to log in again unless you `/logout`.

---

## ⛏ Mining

```
/mine           ← mine 1 token (default)
/mine 5         ← mine 5 tokens
/mine 10 8      ← mine 10 tokens with 8 CPU workers
/stop           ← stop mining anytime
/status         ← live speed & progress
```

The bot sends you updates as each token is minted.

---

## All Commands

| Command | What it does |
|---|---|
| `/start` | Main menu with buttons |
| `/mine [count] [workers]` | Start mining |
| `/stop` | Stop mining |
| `/status` | Speed, hashes, uptime |
| `/balance` | Account balance |
| `/login email` | Request magic link |
| `/complete_login link` | Complete login |
| `/logout` | Log out |
| `/send email amount` | Send RPOW tokens |
| `/activity` | Transaction history |
| `/ledger` | Public ledger stats |
| `/logs` | Recent mining output |
| `/id` | Your Telegram user ID |
| `/help` | Command reference |

---

## How Mining Works

The miner reproduces the exact same proof-of-work that rpow3.com's browser does:

1. **GET /me** — verify session
2. **POST /challenge** — get a challenge (prefix + difficulty)
3. **SHA-256 proof-of-work** — find a nonce where `SHA256(prefix + uint64_le(nonce))` has enough leading zero bits
4. **POST /mint** — submit the solution → receive token

This runs in parallel across multiple CPU cores for speed.

---

## Files

```
rpow3-tg-miner/
├── bot.py              ← Everything in one file
├── requirements.txt    ← Python dependencies
├── .gitignore          ← Keeps secrets out of git
├── README.md           ← This file
├── config.json         ← Created by setup wizard (git-ignored)
└── .rpow-state.json    ← Session cookies (git-ignored)
```

---

## Run 24/7 on a Server

### Linux (systemd)

```bash
sudo nano /etc/systemd/system/rpow-miner.service
```

```ini
[Unit]
Description=RPOW3 Telegram Miner
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/rpow3-tg-miner
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable rpow-miner
sudo systemctl start rpow-miner
sudo journalctl -u rpow-miner -f    # view logs
```

### VPS (Screen)

```bash
screen -S miner
python3 bot.py
# Press Ctrl+A then D to detach
# screen -r miner  to reattach
```

---

## FAQ

**Q: Do I need Node.js?**  
No. This script talks directly to the RPOW3 API using Python.

**Q: Do I need the rpow_cli_miner repo?**  
No. Everything is built into this single `bot.py` file.

**Q: How do I get my Telegram user ID?**  
Run the bot and send `/id`. Or message `@userinfobot` on Telegram.

**Q: Is my password stored?**  
There are no passwords. RPOW3 uses magic-link email authentication. Session cookies are stored locally in `.rpow-state.json` (git-ignored).

**Q: Can I run this on Windows?**  
Yes. `pip install -r requirements.txt` then `python bot.py`.

**Q: Can multiple people use the same bot?**  
Add their Telegram user IDs to `config.json` → `allowed_user_ids` array.

---

## Security

- `config.json` contains your bot token → **never commit it**
- `.rpow-state.json` contains session cookies → **never commit it**
- Both are in `.gitignore` by default
- Set `allowed_user_ids` to restrict who can use your bot

---

## License

MIT
