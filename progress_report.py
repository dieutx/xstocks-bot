"""Send progress report to Telegram while daily reveal is still incomplete."""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import subprocess
import aiohttp

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

# Load simple KEY=VALUE pairs from .env if present so manual runs behave like cron.
env_file = PROJECT_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

from data.db import load_db

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
LOG_FILE = PROJECT_DIR / "run_daily.log"


async def send_progress():
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M:%S")

    total = len(db)
    if total == 0:
        print(f"[{now}] No accounts found; skipping progress report")
        return

    reg = sum(1 for a in db if a.get("registered"))

    verify = subprocess.run(
        [str(PROJECT_DIR / "venv/bin/python3"), str(PROJECT_DIR / "verify_daily_status.py")],
        capture_output=True,
        text=True,
    )
    is_reveal_complete = verify.returncode == 0

    if is_reveal_complete:
        print(f"[{now}] Daily reveal already complete; no progress message needed")
        return

    try:
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        else:
            lines = []
        last_batch = ""
        for line in reversed(lines):
            if "Batch" in line and "done" in line:
                last_batch = line.strip().split("] ", 1)[-1] if "] " in line else line.strip()
                break
        if not last_batch:
            last_batch = "N/A"
    except Exception:
        last_batch = "N/A"

    running = "🟢 Reveal complete" if is_reveal_complete else "🟡 Waiting / Partial"
    remaining_reg = total - reg

    msg = (
        f"📊 <b>XStock Bot — Progress Update</b>\n"
        f"🕐 {now}\n\n"
        f"📝 Registered: <b>{reg}/{total}</b> ({reg * 100 // total}%)\n"
        f"🎯 Reveal today: <b>incomplete</b>\n"
        f"⏳ Remaining: <b>{remaining_reg}</b> registration\n\n"
        f"Status: {running}\n"
        f"Last: {last_batch}"
    )

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[{now}] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID; skipping send")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                print(f"[{now}] Progress sent to Telegram")
            else:
                print(f"[{now}] Failed: {await resp.text()}")


if __name__ == "__main__":
    asyncio.run(send_progress())
