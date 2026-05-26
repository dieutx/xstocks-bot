#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from core.http_client import create_session, api_get, api_put, generate_fingerprint, weighted_delay
from run_batched import API_BASE, SPIN_MESSAGE_PREFIX, get_signer, sign_message

DB_FILE = PROJECT_DIR / "data" / "accounts.json"


async def reveal_for_account(acc: dict) -> dict:
    address = acc["address"]
    wallet_type = acc["wallet_type"]
    fp = acc.get("fingerprint") or generate_fingerprint()
    etags = acc.get("etags") or {}
    session = None
    short = f"{address[:6]}...{address[-4:]}"
    try:
        session = await create_session(acc.get("proxy"), fp)
        signer = get_signer(acc)

        dash_status, dashboard, dash_etag = await api_get(
            session,
            f"{API_BASE}/xdrop-user/{address}/dashboard",
            fp,
            etags,
        )
        if dash_etag:
            etags[f"dashboard-{address}"] = dash_etag
        if dash_status != 200 or not isinstance(dashboard, dict):
            return {"account": short, "status": "dashboard_failed", "http": dash_status}

        data = dashboard.get("data") or dashboard
        if not isinstance(data, dict):
            return {"account": short, "status": "dashboard_payload_invalid"}

        spin_revealed = data.get("dailySpinMultiplierRevealed")
        if spin_revealed is not False:
            acc["fingerprint"] = fp
            acc["etags"] = etags
            return {"account": short, "status": "already_revealed"}

        sign_ts = int(time.time())
        spin_msg = f"{SPIN_MESSAGE_PREFIX} | {sign_ts}"
        sig = sign_message(signer, spin_msg, wallet_type)
        payload = {
            "walletAddress": address,
            "signature": sig,
            "signMethod": "message",
            "signTimestamp": sign_ts,
        }

        put_status, put_data = await api_put(
            session,
            f"{API_BASE}/xdrop-user/daily-spin-multiplier",
            payload,
            fp,
        )
        await asyncio.sleep(weighted_delay(1.0, 2.0))

        dash2_status, dashboard2, dash2_etag = await api_get(
            session,
            f"{API_BASE}/xdrop-user/{address}/dashboard",
            fp,
        )
        if dash2_etag:
            etags[f"dashboard-{address}"] = dash2_etag

        confirmed = None
        if dash2_status == 200 and isinstance(dashboard2, dict):
            data2 = dashboard2.get("data") or dashboard2
            if isinstance(data2, dict):
                confirmed = data2.get("dailySpinMultiplierRevealed")

        acc["fingerprint"] = fp
        acc["etags"] = etags
        if confirmed is True:
            return {"account": short, "status": "revealed", "http": put_status}
        return {
            "account": short,
            "status": "reveal_unconfirmed",
            "http": put_status,
            "response_preview": str(put_data)[:120],
        }
    except Exception as exc:
        return {"account": short, "status": "exception", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if session is not None:
            await session.close()


async def main() -> int:
    if not DB_FILE.exists():
        print("NO_ACCOUNTS_DB")
        return 2

    accounts = json.loads(DB_FILE.read_text())
    registered = [acc for acc in accounts if acc.get("registered", True)]
    if not registered:
        print("NO_REGISTERED_ACCOUNTS")
        return 2

    results = []
    ok = True
    for acc in registered:
        result = await reveal_for_account(acc)
        results.append(result)
        if result["status"] not in {"already_revealed", "revealed"}:
            ok = False

    DB_FILE.write_text(json.dumps(accounts, indent=2))
    print(json.dumps(results, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
