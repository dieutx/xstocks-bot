"""Send progress report to Telegram every 30 minutes."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.db import load_db
from datetime import datetime
from utils.telegram import send_telegram_summary
import aiohttp

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

async def send_progress():
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M:%S")
    
    total = len(db)
    reg = sum(1 for a in db if a.get("registered"))
    gm = sum(1 for a in db if a.get("gm_last_date") == today)
    
    # Check if process is still running
    import subprocess
    result = subprocess.run(["pgrep", "-f", "run_batched"], capture_output=True)
    running = "🟢 Running" if result.returncode == 0 else "🔴 Stopped"
    
    # Get last log line
    try:
        with open("/root/claude-xstocks/run_register.log") as f:
            lines = f.readlines()
            last_batch = ""
            for line in reversed(lines):
                if "Batch" in line and "done" in line:
                    last_batch = line.strip().split("] ", 1)[-1] if "] " in line else line.strip()
                    break
    except:
        last_batch = "N/A"
    
    msg = (
        f"📊 <b>XStock Bot — Progress Update</b>\n"
        f"🕐 {now}\n\n"
        f"📝 Registered: <b>{reg}/{total}</b> ({reg*100//total}%)\n"
        f"✅ GM today: <b>{gm}/{total}</b> ({gm*100//total}%)\n"
        f"⏳ Remaining: <b>{total - reg}</b> registration, <b>{total - gm}</b> GM\n\n"
        f"Status: {running}\n"
        f"Last: {last_batch}"
    )
    
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
