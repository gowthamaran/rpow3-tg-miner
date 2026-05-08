#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║          RPOW3  CLI  MINER  +  TELEGRAM  BOT BY MARAN                ║
║          ────────────────────────────────────                ║
║  One-file miner that talks directly to rpow3.com API.       ║
║  No Node.js needed.  No rpow_cli_miner repo needed.         ║
║  Just run: python3 bot.py  and answer the questions.        ║
╚══════════════════════════════════════════════════════════════╝

HOW IT WORKS
────────────
1. Run this script.  It asks you a few questions (bot token, email, etc.)
2. It logs in to rpow3.com via magic-link email.
3. Mining starts automatically and you control everything from Telegram.

REQUIREMENTS
────────────
  Python 3.10+
  pip install python-telegram-bot aiohttp

TELEGRAM COMMANDS (after setup)
───────────────────────────────
  /start   — Main menu with buttons
  /mine    — Start mining  (or tap ⛏ button)
  /stop    — Stop mining
  /status  — Live stats
  /balance — Account info & balance
  /send    — Send tokens
  /logs    — Recent mining output
  /help    — All commands
"""

import asyncio
import hashlib
import json
import logging
import os
import struct
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from multiprocessing import Process, Queue, Value
from pathlib import Path
from typing import Optional

# ─── check deps before anything else ─────────────────────────────────────────
def _check_deps():
    missing = []
    try:
        import telegram  # noqa: F401
    except ImportError:
        missing.append("python-telegram-bot")
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        missing.append("aiohttp")
    if missing:
        print("\n❌  Missing dependencies.  Run this first:\n")
        print(f"    pip install {' '.join(missing)}\n")
        sys.exit(1)

_check_deps()

import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# ═════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ═════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)
log = logging.getLogger("rpow")

# ═════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════

# --- API hosts (rpow3 follows the same API shape as rpow2) ---
API_ORIGINS = [
    "https://api.rpow3.com",
    "https://rpow3.com/api",
    "https://api.rpow2.com",
]

STATE_FILE = Path(__file__).parent / ".rpow-state.json"
CONFIG_FILE = Path(__file__).parent / "config.json"

HEADERS_BASE = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "RPOW-CLI-TG/1.0",
}

# ═════════════════════════════════════════════════════════════════════════════
#  CONFIG  —  persisted to config.json
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    bot_token: str = ""
    allowed_user_ids: list[int] = field(default_factory=list)
    email: str = ""
    default_workers: int = 4
    default_mine_count: int = 1
    api_origin: str = ""  # resolved at runtime

    def save(self):
        CONFIG_FILE.write_text(json.dumps(self.__dict__, indent=2))

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            c = cls()
            for k, v in data.items():
                if hasattr(c, k):
                    setattr(c, k, v)
            return c
        return cls()


# ═════════════════════════════════════════════════════════════════════════════
#  SESSION STATE  —  cookies & challenge stored in .rpow-state.json
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class SessionState:
    cookies: dict = field(default_factory=dict)
    challenge_id: str = ""
    nonce_prefix: str = ""  # hex
    difficulty: int = 0
    nonce_start: int = 0  # resume offset
    email: str = ""

    def save(self):
        STATE_FILE.write_text(json.dumps(self.__dict__, indent=2))

    @classmethod
    def load(cls) -> "SessionState":
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text())
                s = cls()
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
                return s
            except Exception:
                pass
        return cls()


# ═════════════════════════════════════════════════════════════════════════════
#  RPOW  API  CLIENT  (pure Python, no Node.js)
# ═════════════════════════════════════════════════════════════════════════════

class RPOWClient:
    """Async HTTP client for the RPOW3 API."""

    def __init__(self, config: Config):
        self.config = config
        self.state = SessionState.load()
        self._session: Optional[aiohttp.ClientSession] = None
        self._api: str = ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                headers=HEADERS_BASE,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            # restore cookies
            for name, val in self.state.cookies.items():
                self._session.cookie_jar.update_cookies({name: val})
        return self._session

    async def _resolve_api(self) -> str:
        """Try each API origin and return the first one that responds."""
        if self._api:
            return self._api
        if self.config.api_origin:
            self._api = self.config.api_origin
            return self._api

        for origin in API_ORIGINS:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as tmp:
                    async with tmp.get(f"{origin}/ledger") as r:
                        if r.status < 500:
                            self._api = origin
                            self.config.api_origin = origin
                            self.config.save()
                            log.info(f"API origin resolved: {origin}")
                            return origin
            except Exception:
                continue

        # fallback
        self._api = API_ORIGINS[0]
        return self._api

    def _save_cookies(self, session: aiohttp.ClientSession):
        cookies = {}
        for cookie in session.cookie_jar:
            cookies[cookie.key] = cookie.value
        self.state.cookies = cookies
        self.state.save()

    # ── API calls ──────────────────────────────────────────────────────────

    async def request_login(self, email: str) -> str:
        """POST /auth/request  →  sends magic link to email."""
        api = await self._resolve_api()
        s = await self._get_session()
        async with s.post(f"{api}/auth/request", json={"email": email}) as r:
            body = await r.text()
            if r.status == 200:
                self.state.email = email
                self.state.save()
                return f"✅ Magic link sent to {email}\nCheck your inbox!"
            elif r.status == 429:
                return "⚠️ Rate limited — wait a minute then try again."
            else:
                return f"❌ Login request failed ({r.status}): {body}"

    async def complete_login(self, magic_link: str) -> str:
        """Follow the magic link to get session cookies."""
        s = await self._get_session()
        try:
            async with s.get(magic_link, allow_redirects=True) as r:
                self._save_cookies(s)
                if r.status < 400:
                    # verify session
                    api = await self._resolve_api()
                    async with s.get(f"{api}/me") as r2:
                        if r2.status == 200:
                            data = await r2.json()
                            self._save_cookies(s)
                            return f"✅ Logged in!\n\n{json.dumps(data, indent=2)}"
                        else:
                            return f"⚠️ Link followed but /me failed ({r2.status})"
                else:
                    return f"❌ Magic link returned {r.status}"
        except Exception as e:
            return f"❌ Error following link: {e}"

    async def get_me(self) -> dict | str:
        """GET /me"""
        api = await self._resolve_api()
        s = await self._get_session()
        async with s.get(f"{api}/me") as r:
            self._save_cookies(s)
            if r.status == 200:
                return await r.json()
            elif r.status == 401:
                return "❌ Not logged in. Use /login first."
            else:
                return f"❌ /me failed ({r.status}): {await r.text()}"

    async def get_challenge(self) -> dict | str:
        """POST /challenge"""
        api = await self._resolve_api()
        s = await self._get_session()
        async with s.post(f"{api}/challenge") as r:
            self._save_cookies(s)
            if r.status == 200:
                data = await r.json()
                self.state.challenge_id = data.get("id", data.get("challenge_id", ""))
                self.state.nonce_prefix = data.get("nonce_prefix", data.get("prefix", ""))
                self.state.difficulty = data.get("difficulty", 0)
                self.state.nonce_start = 0
                self.state.save()
                return data
            else:
                return f"❌ /challenge failed ({r.status}): {await r.text()}"

    async def submit_mint(self, challenge_id: str, nonce: int) -> dict | str:
        """POST /mint"""
        api = await self._resolve_api()
        s = await self._get_session()
        payload = {
            "challenge_id": challenge_id,
            "solution_nonce": nonce,
        }
        async with s.post(f"{api}/mint", json=payload) as r:
            self._save_cookies(s)
            if r.status == 200:
                return await r.json()
            else:
                return f"❌ /mint failed ({r.status}): {await r.text()}"

    async def send_rpow(self, to_email: str, amount: int) -> str:
        """POST /send"""
        import uuid
        api = await self._resolve_api()
        s = await self._get_session()
        payload = {
            "recipient_email": to_email,
            "amount": amount,
            "idempotency_key": str(uuid.uuid4()),
        }
        async with s.post(f"{api}/send", json=payload) as r:
            self._save_cookies(s)
            if r.status == 200:
                return f"✅ Sent {amount} RPOW to {to_email}"
            else:
                return f"❌ /send failed ({r.status}): {await r.text()}"

    async def get_activity(self) -> str:
        """GET /activity"""
        api = await self._resolve_api()
        s = await self._get_session()
        async with s.get(f"{api}/activity") as r:
            self._save_cookies(s)
            body = await r.text()
            if r.status == 200:
                try:
                    return json.dumps(json.loads(body), indent=2)
                except Exception:
                    return body
            else:
                return f"❌ /activity failed ({r.status}): {body}"

    async def get_ledger(self) -> str:
        """GET /ledger — no auth needed"""
        api = await self._resolve_api()
        s = await self._get_session()
        async with s.get(f"{api}/ledger") as r:
            body = await r.text()
            if r.status == 200:
                try:
                    return json.dumps(json.loads(body), indent=2)
                except Exception:
                    return body
            else:
                return f"❌ /ledger failed ({r.status}): {body}"

    async def logout(self) -> str:
        """POST /auth/logout"""
        api = await self._resolve_api()
        s = await self._get_session()
        async with s.post(f"{api}/auth/logout") as r:
            self.state = SessionState()
            self.state.save()
            if r.status == 200:
                return "✅ Logged out."
            else:
                return f"Logged out locally (server returned {r.status})."

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ═════════════════════════════════════════════════════════════════════════════
#  SHA-256  PROOF-OF-WORK  MINER  (pure Python — runs in a worker process)
# ═════════════════════════════════════════════════════════════════════════════

def _mine_worker(
    prefix_hex: str,
    difficulty: int,
    start_nonce: int,
    end_nonce: int,
    result_queue: Queue,
    stop_flag,
    stats_queue: Queue,
):
    """
    Worker process: compute SHA-256(prefix || nonce_le_u64) and find
    a nonce whose hash has `difficulty` leading zero bits.

    This matches the algorithm from rpow-native-miner.c:
      hash = SHA256( nonce_prefix_bytes || uint64_le(nonce) )
      if leading_zero_bits(hash) >= difficulty: solution found
    """
    prefix_bytes = bytes.fromhex(prefix_hex)
    target_bytes = difficulty // 8
    target_bits = difficulty % 8
    count = 0
    report_interval = 50_000  # report speed every N hashes

    for nonce in range(start_nonce, end_nonce):
        if stop_flag.value:
            return

        # SHA-256( prefix || uint64_le(nonce) )
        data = prefix_bytes + struct.pack("<Q", nonce)
        h = hashlib.sha256(data).digest()

        # check leading zero bits
        ok = True
        for i in range(target_bytes):
            if h[i] != 0:
                ok = False
                break
        if ok and target_bits > 0:
            mask = (0xFF << (8 - target_bits)) & 0xFF
            if (h[target_bytes] & mask) != 0:
                ok = False

        if ok:
            result_queue.put(nonce)
            return

        count += 1
        if count % report_interval == 0:
            stats_queue.put(count)
            count = 0

    # exhausted range without finding
    stats_queue.put(count)


class MinerEngine:
    """Manages multi-process PoW mining."""

    def __init__(self):
        self.processes: list[Process] = []
        self.stop_flag = Value("i", 0)
        self.result_queue = Queue()
        self.stats_queue = Queue()
        self.total_hashes = 0
        self.mining = False
        self.started_at = 0.0
        self.tokens_mined = 0
        self.current_speed = "—"
        self.log_lines: list[str] = []
        self._target_count = 0

    def _log(self, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_lines.append(line)
        if len(self.log_lines) > 100:
            self.log_lines = self.log_lines[-100:]
        log.info(msg)

    async def mine_token(self, client: RPOWClient, workers: int) -> str:
        """Mine a single token: get challenge → solve PoW → submit mint."""
        # 1. Get challenge
        self._log("Requesting challenge...")
        challenge = await client.get_challenge()
        if isinstance(challenge, str):
            return challenge  # error message

        cid = challenge.get("id", challenge.get("challenge_id", ""))
        prefix = challenge.get("nonce_prefix", challenge.get("prefix", ""))
        difficulty = challenge.get("difficulty", 0)

        if not cid or not prefix or not difficulty:
            return f"❌ Bad challenge response: {json.dumps(challenge)}"

        self._log(f"Challenge: id={cid[:12]}... difficulty={difficulty} prefix={prefix[:16]}...")

        # 2. Solve PoW
        solution = await self._solve(prefix, difficulty, workers)
        if solution is None:
            return "❌ Mining was stopped before a solution was found."

        self._log(f"✅ Solution found! nonce={solution}")

        # 3. Submit
        self._log("Submitting mint...")
        result = await client.submit_mint(cid, solution)
        if isinstance(result, dict):
            self.tokens_mined += 1
            self._log(f"🎉 Minted! Total: {self.tokens_mined}")
            return f"🎉 Token minted! (nonce={solution})\n{json.dumps(result, indent=2)}"
        else:
            return result  # error string

    async def _solve(self, prefix_hex: str, difficulty: int, num_workers: int) -> Optional[int]:
        """Launch workers and wait for a solution."""
        self.stop_flag.value = 0
        self.total_hashes = 0

        # split nonce range across workers
        chunk = (2**64) // num_workers
        self.processes = []

        for i in range(num_workers):
            start = i * chunk
            end = start + chunk if i < num_workers - 1 else 2**64
            p = Process(
                target=_mine_worker,
                args=(prefix_hex, difficulty, start, end,
                      self.result_queue, self.stop_flag, self.stats_queue),
                daemon=True,
            )
            p.start()
            self.processes.append(p)

        self._log(f"Mining with {num_workers} workers...")
        start_time = time.time()

        # poll for result
        while True:
            # drain stats
            while not self.stats_queue.empty():
                try:
                    self.total_hashes += self.stats_queue.get_nowait()
                except Exception:
                    break

            elapsed = time.time() - start_time
            if elapsed > 0:
                rate = self.total_hashes / elapsed
                if rate > 1_000_000:
                    self.current_speed = f"{rate/1_000_000:.2f} MH/s"
                elif rate > 1_000:
                    self.current_speed = f"{rate/1_000:.1f} KH/s"
                else:
                    self.current_speed = f"{rate:.0f} H/s"

            # check for solution
            if not self.result_queue.empty():
                nonce = self.result_queue.get()
                self.stop_flag.value = 1
                self._cleanup_workers()
                return nonce

            # check if stopped externally
            if self.stop_flag.value:
                self._cleanup_workers()
                return None

            # check if all workers died
            if all(not p.is_alive() for p in self.processes):
                if not self.result_queue.empty():
                    return self.result_queue.get()
                self._cleanup_workers()
                return None

            await asyncio.sleep(0.3)

    def _cleanup_workers(self):
        for p in self.processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=3)
        self.processes = []

    def stop(self):
        self.stop_flag.value = 1
        self.mining = False
        self._cleanup_workers()


# ═════════════════════════════════════════════════════════════════════════════
#  MINING SESSION  (runs mine_token in a loop)
# ═════════════════════════════════════════════════════════════════════════════

class MiningSession:
    def __init__(self, client: RPOWClient, engine: MinerEngine):
        self.client = client
        self.engine = engine
        self._task: Optional[asyncio.Task] = None
        self.running = False
        self.target_count = 0

    async def start(self, count: int, workers: int, chat_id: int, bot):
        if self.running:
            return "⚠️ Already mining. /stop first."
        self.running = True
        self.engine.mining = True
        self.engine.started_at = time.time()
        self.engine.tokens_mined = 0
   
