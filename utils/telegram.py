"""
Telegram notification for xStocks bot daily run summaries.
"""

import aiohttp
from datetime import datetime
from pathlib import Path

import os

# Load .env for direct/manual usage paths too.
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def build_summary_message(results: list[dict], task_name: str) -> str:
    """
    Build a Telegram-friendly summary message from task results.

    Args:
        results: List of result dicts with keys: index, address, status, details.
        task_name: Name of the task that was run.

    Returns:
        Formatted message string.
    """
    total = len(results)
    success = sum(1 for r in results if r.get("status") == "SUCCESS")
    failed = total - success

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"🤖 <b>xStocks Bot — {task_name}</b>",
        f"📅 {now}",
        f"",
        f"✅ Success: <b>{success}/{total}</b>",
    ]

    if failed > 0:
        lines.append(f"❌ Failed: <b>{failed}/{total}</b>")

    # List failed accounts if any
    failed_results = [r for r in results if r.get("status") != "SUCCESS"]
    if failed_results:
        lines.append("")
        lines.append("<b>Failed accounts:</b>")
        for r in failed_results:
            addr = r.get("address", "?")
            short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
            details = r.get("details", "unknown error")
            lines.append(f"  • {short_addr}: {details}")

    # Show a few success examples with points
    success_with_points = [
        r for r in results
        if r.get("status") == "SUCCESS" and "Points:" in r.get("details", "")
    ]
    if success_with_points:
        lines.append("")
        lines.append(f"<b>Sample results ({min(5, len(success_with_points))}/{success}):</b>")
        for r in success_with_points[:5]:
            addr = r.get("address", "?")
            short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
            details = r.get("details", "")
            lines.append(f"  • {short_addr}: {details}")

    return "\n".join(lines)


async def send_telegram_summary(results: list[dict], task_name: str) -> bool:
    """
    Send task results summary to Telegram group.

    Args:
        results: List of result dicts from task run.
        task_name: Name of the task.

    Returns:
        True if message sent successfully, False otherwise.
    """
    message = build_summary_message(results, task_name)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                print(f"  Telegram send failed [{resp.status}]: {body[:200]}")
                return False
    except Exception as e:
        print(f"  Telegram send error: {e}")
        return False
