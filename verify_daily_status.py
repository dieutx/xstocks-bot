#!/usr/bin/env python3
"""Verify xStocks daily status across registered accounts.

Exit codes:
  0 = all registered accounts have GM done and daily spin revealed
  1 = at least one account is incomplete or unreachable
  2 = no accounts configured
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ns = str(PROJECT_DIR)
if ns not in sys.path:
    sys.path.insert(0, ns)

from core.http_client import api_get, create_session, generate_fingerprint  # noqa: E402

API_BASE = "https://points-api.xstocks.fi/api/v1"
DB_FILE = PROJECT_DIR / "data" / "accounts.json"
CONCURRENCY = 10


async def check_account(acc: dict, sem: asyncio.Semaphore) -> dict:
    address = acc["address"]
    proxy = acc.get("proxy")
    fp = acc.get("fingerprint") or generate_fingerprint()
    session = None
    async with sem:
        try:
            session = await create_session(proxy, fp)
            status, dashboard, _ = await api_get(
                session,
                f"{API_BASE}/xdrop-user/{address}/dashboard",
                fp,
                acc.get("etags") or {},
            )
            if status != 200 or not isinstance(dashboard, dict):
                return {
                    "address": address,
                    "ok": False,
                    "reason": f"dashboard_status={status}",
                }

            data = dashboard.get("data") or dashboard
            if not isinstance(data, dict):
                return {
                    "address": address,
                    "ok": False,
                    "reason": "dashboard_payload_not_dict",
                }

            gm_remaining = int(data.get("gmClicksRemaining") or 0)
            spin_revealed = data.get("dailySpinMultiplierRevealed")
            ok = gm_remaining == 0 and spin_revealed is not False
            return {
                "address": address,
                "ok": ok,
                "gm_remaining": gm_remaining,
                "spin_revealed": spin_revealed,
                "reason": None if ok else f"gm_remaining={gm_remaining}, spin_revealed={spin_revealed}",
            }
        except Exception as exc:
            return {
                "address": address,
                "ok": False,
                "reason": f"exception={type(exc).__name__}: {exc}",
            }
        finally:
            if session is not None:
                await session.close()


async def main() -> int:
    if not DB_FILE.exists():
        print("NO_ACCOUNTS_DB")
        return 2

    accounts = json.loads(DB_FILE.read_text())
    if not accounts:
        print("NO_ACCOUNTS_CONFIGURED")
        return 2

    registered = [acc for acc in accounts if acc.get("registered", True)]
    if not registered:
        print("NO_REGISTERED_ACCOUNTS")
        return 2

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(check_account(acc, sem) for acc in registered))
    incomplete = [r for r in results if not r["ok"]]

    print(f"registered={len(registered)} incomplete={len(incomplete)}")
    for row in incomplete[:20]:
        short = f"{row['address'][:6]}...{row['address'][-4:]}"
        print(f"INCOMPLETE {short} {row['reason']}")

    return 0 if not incomplete else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
