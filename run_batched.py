"""
Batched execution engine for xStocks bot with anti-detection.
Uses curl_cffi for Chrome TLS fingerprint, per-account browser identity,
realistic request flow, and weighted delays.
"""

import asyncio
import random
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.db import (
    load_db, save_db, mark_registered, mark_gm_done, make_batches,
    get_accounts_needing_gm, find_account,
)
from core.http_client import (
    generate_fingerprint, create_session, api_get, api_post, api_put,
    weighted_delay,
)
from core.account import BotAccount
from core.solana_account import SolanaAccount
from config import REFERRAL_CODE, SAY_GM_MESSAGE, REGISTER_MESSAGE
from utils.logger import log_info, log_success, log_error, log_warning, print_banner
from utils.telegram import send_telegram_summary, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API_BASE = "https://api.backed.fi/xdrop/api/v1"
SPIN_MESSAGE = "Daily Spin Multiplier"


async def alert_telegram(message: str) -> None:
    """Send an immediate alert to Telegram."""
    from curl_cffi.requests import AsyncSession
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with AsyncSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception:
        pass


def get_signer(acc_data: dict) -> BotAccount | SolanaAccount:
    """Create account object just for signing (no session needed)."""
    if acc_data["wallet_type"] == "Evm":
        pk = acc_data["private_key"]
        if not pk.startswith("0x"):
            pk = f"0x{pk}"
        return BotAccount(index=0, private_key=pk, proxy=None)
    else:
        return SolanaAccount(index=0, private_key=acc_data["private_key"], proxy=None)


def sign_message(signer: BotAccount | SolanaAccount, message: str, wallet_type: str) -> str:
    """Sign a message and return formatted signature."""
    raw = signer.sign_message(message)
    if wallet_type == "Evm":
        return raw if raw.startswith("0x") else f"0x{raw}"
    return raw  # Solana: already base64


async def run_single_account(
    acc_data: dict,
    mode: str,
    db: list[dict],
) -> dict:
    """
    Run full browser-like flow for one account.
    Flow: xdrop-config → check user → register if needed → dashboard → spin → GM
    """
    address = acc_data["address"]
    wallet_type = acc_data["wallet_type"]
    proxy = acc_data.get("proxy")
    short_addr = f"{address[:6]}...{address[-4:]}"

    result = {"address": address, "status": "FAILED", "details": ""}

    # Get or generate fingerprint
    if not acc_data.get("fingerprint"):
        acc_data["fingerprint"] = generate_fingerprint()
    fp = acc_data["fingerprint"]
    etags = acc_data.get("etags") or {}

    session = None
    try:
        session = await create_session(proxy, fp)
        signer = get_signer(acc_data)

        # --- Registration mode: full browser flow ---
        if mode == "register_gm":
            # Step 1: GET /xdrop-config (browser preflight)
            status, _, etag = await api_get(session, f"{API_BASE}/xdrop-config", fp, etags)
            if etag:
                etags["xdrop-config"] = etag
            await asyncio.sleep(weighted_delay(0.3, 1.0))

        # --- Step 2: Registration ---
        if mode == "register_gm" and not acc_data.get("registered"):
            # Check if account exists
            status, data, _ = await api_get(session, f"{API_BASE}/xdrop-user/{address}", fp)

            if status == 200 and data:
                log_info("Already registered", 0, short_addr)
                mark_registered(db, address)
            elif status == 404 or (status == 200 and not data):
                # Register
                log_info(f"Registering {wallet_type}...", 0, short_addr)
                sig = sign_message(signer, REGISTER_MESSAGE, wallet_type)
                payload = {
                    "walletAddress": address,
                    "walletType": wallet_type,
                    "signature": sig,
                    "referredBy": REFERRAL_CODE,
                }
                status, data = await api_post(session, f"{API_BASE}/xdrop-user", payload, fp)

                if status in (200, 201):
                    log_success("Registered!", 0, short_addr)
                    mark_registered(db, address)
                elif status in (400, 409) and data and "already exists" in str(data).lower():
                    log_info("Already registered (confirmed)", 0, short_addr)
                    mark_registered(db, address)
                else:
                    log_error(f"Registration failed [{status}]: {str(data)[:100]}", 0, short_addr)
                    result["details"] = f"Registration failed [{status}]"
                    return result

                await asyncio.sleep(weighted_delay(1.0, 3.0))
            else:
                log_warning(f"User check failed [{status}], skipping registration", 0, short_addr)

        # --- Step 3: Check if GM needed ---
        today = datetime.now().strftime("%Y-%m-%d")
        if acc_data.get("gm_last_date") == today:
            result["status"] = "SUCCESS"
            result["details"] = "GM: already done today"
            return result

        # --- Step 4: Dashboard ---
        if mode == "register_gm":
            # Full flow: dashboard + points-breakdown in parallel
            await asyncio.sleep(weighted_delay(0.5, 1.5))
            dash_task = api_get(session, f"{API_BASE}/xdrop-user/{address}/dashboard", fp, etags)
            pts_task = api_get(session, f"{API_BASE}/xdrop-user/{address}/points-breakdown", fp, etags)
            (dash_status, dashboard, dash_etag), (pts_status, _, pts_etag) = await asyncio.gather(dash_task, pts_task)
        else:
            # Fast GM: dashboard only, no extra calls
            dash_status, dashboard, dash_etag = await api_get(session, f"{API_BASE}/xdrop-user/{address}/dashboard", fp, etags)
            pts_etag = None

        if dash_etag:
            etags[f"dashboard-{address}"] = dash_etag
        if pts_etag:
            etags[f"points-{address}"] = pts_etag

        if dash_status != 200 or not dashboard:
            if not acc_data.get("registered", True):
                result["details"] = "Dashboard failed"
                return result
            # Try GM anyway
            dashboard = None

        dash_data = (dashboard.get("data") or dashboard) if dashboard else {}
        gm_remaining = int(dash_data.get("gmClicksRemaining", 0)) if dash_data else 1
        total_points = dash_data.get("totalPoints", "?") if dash_data else "?"

        # --- Step 5: Daily Spin Multiplier (with retry on 429/500) ---
        spin_revealed = dash_data.get("dailySpinMultiplierRevealed") if dash_data else None
        if spin_revealed is False:
            log_info("Revealing spin multiplier...", 0, short_addr)
            sig = sign_message(signer, SPIN_MESSAGE, wallet_type)
            spin_payload = {"walletAddress": address, "signature": sig}

            for spin_attempt in range(1, 4):
                spin_status, spin_data = await api_put(
                    session, f"{API_BASE}/xdrop-user/daily-spin-multiplier", spin_payload, fp
                )
                if spin_status in (200, 201):
                    log_success("Spin revealed!", 0, short_addr)
                    break
                elif spin_status in (400, 409):
                    log_info("Spin already done", 0, short_addr)
                    break
                elif spin_status == 429:
                    wait = weighted_delay(5.0, 15.0)
                    log_warning(f"Spin rate limited (429), waiting {wait:.0f}s... (attempt {spin_attempt}/3)", 0, short_addr)
                    await asyncio.sleep(wait)
                elif spin_status == 500:
                    wait = weighted_delay(3.0, 8.0)
                    log_warning(f"Spin got 500, retrying in {wait:.0f}s... (attempt {spin_attempt}/3)", 0, short_addr)
                    await asyncio.sleep(wait)
                else:
                    log_warning(f"Spin failed [{spin_status}]", 0, short_addr)
                    break

            if mode == "register_gm":
                await asyncio.sleep(weighted_delay(0.5, 2.0))
            else:
                await asyncio.sleep(weighted_delay(0.1, 0.5))

        # --- Step 6: Say GM ---
        if gm_remaining == 0:
            mark_gm_done(db, address)
            result["status"] = "SUCCESS"
            result["details"] = f"GM: already done | Points: {total_points}"
            return result

        if mode == "register_gm":
            await asyncio.sleep(weighted_delay(1.0, 3.0))
        else:
            await asyncio.sleep(weighted_delay(0.1, 0.5))

        log_info(f"Say GM (remaining: {gm_remaining})...", 0, short_addr)
        sig = sign_message(signer, SAY_GM_MESSAGE, wallet_type)
        gm_payload = {"walletAddress": address, "signature": sig}

        # Retry GM up to 3 times with dashboard verification
        gm_success = False
        for gm_attempt in range(1, 4):
            gm_status, gm_data = await api_post(
                session, f"{API_BASE}/xdrop-user/say-gm", gm_payload, fp
            )

            if gm_status == 200 and gm_data:
                inner = gm_data.get("data") or gm_data if isinstance(gm_data, dict) else {}
                pts_added = inner.get("pointsAdded", "?")
                log_success(f"GM done! +{pts_added} pts", 0, short_addr)
                mark_gm_done(db, address)
                result["status"] = "SUCCESS"
                result["details"] = f"GM: +{pts_added} pts | Total: {total_points}"
                gm_success = True
                break
            elif gm_status in (400, 409):
                log_info("GM already done (click limit)", 0, short_addr)
                mark_gm_done(db, address)
                result["status"] = "SUCCESS"
                result["details"] = f"GM: already done | Points: {total_points}"
                gm_success = True
                break
            else:
                # 500 or other error — check dashboard before retrying
                log_warning(f"GM attempt {gm_attempt}/3 failed [{gm_status}], checking dashboard...", 0, short_addr)
                await asyncio.sleep(weighted_delay(2.0, 5.0))
                _, dash2, _ = await api_get(session, f"{API_BASE}/xdrop-user/{address}/dashboard", fp)
                if dash2:
                    d2 = (dash2.get("data") or dash2) if isinstance(dash2, dict) else {}
                    if int(d2.get("gmClicksRemaining", 1)) == 0:
                        mark_gm_done(db, address)
                        result["status"] = "SUCCESS"
                        result["details"] = "GM: confirmed via dashboard"
                        gm_success = True
                        break
                    log_info(f"Clicks still remaining, retrying...", 0, short_addr)
                    await asyncio.sleep(weighted_delay(3.0, 8.0))

        if not gm_success:
            result["details"] = f"GM failed after 3 attempts"
            log_error("GM failed after all retries", 0, short_addr)

        # Save etags back
        acc_data["etags"] = etags
        return result

    except Exception as e:
        err_msg = str(e) or type(e).__name__
        result["details"] = f"Error: {err_msg[:80]}"
        log_error(f"Account error: {err_msg}", 0, short_addr)
        return result

    finally:
        if session:
            await session.close()


async def run_batch(
    batch: list[dict],
    batch_num: int,
    total_batches: int,
    mode: str,
    db: list[dict],
) -> list[dict]:
    """Run a batch of accounts concurrently."""
    evm_count = sum(1 for a in batch if a["wallet_type"] == "Evm")
    sol_count = len(batch) - evm_count
    log_info(f"=== Batch {batch_num}/{total_batches} === {len(batch)} accounts ({evm_count} EVM, {sol_count} Sol)")

    tasks = [run_single_account(acc, mode, db) for acc in batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed.append({
                "address": batch[i]["address"],
                "status": "FAILED",
                "details": f"Exception: {str(r)[:80]}",
            })
        elif isinstance(r, dict):
            processed.append(r)

    return processed


async def run_all_batched(mode: str = "register_gm") -> None:
    """Main entry point."""
    print_banner()
    db = load_db()

    if not db:
        log_error("No accounts in database.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if mode == "register_gm":
        pending = [a for a in db if not a.get("registered") or a.get("gm_last_date") != today]
    else:
        pending = get_accounts_needing_gm(db, today)

    if not pending:
        log_info("All accounts up to date!")
        return

    log_info(f"Pending: {len(pending)} accounts")

    # Global startup jitter (0-60s for cron, skip for manual)
    if os.environ.get("CRON_RUN"):
        jitter = random.uniform(0, 60)
        log_info(f"Startup jitter: {jitter:.0f}s")
        await asyncio.sleep(jitter)

    batches = make_batches(pending, min_size=40, max_size=60)
    log_info(f"Split into {len(batches)} batches")

    all_results = []
    for batch_num, batch in enumerate(batches, 1):
        results = await run_batch(batch, batch_num, len(batches), mode, db)
        all_results.extend(results)

        save_db(db)

        success = sum(1 for r in results if r.get("status") == "SUCCESS")
        failed_in_batch = [r for r in results if r.get("status") != "SUCCESS"]
        log_info(f"Batch {batch_num} done: {success}/{len(results)} success")

        if failed_in_batch:
            fails = "\n".join(f"  • {r['address'][:10]}...: {r['details']}" for r in failed_in_batch[:5])
            await alert_telegram(f"🚨 <b>[xStocks Bot] Batch {batch_num}: {len(failed_in_batch)} failed</b>\n{fails}")

        if batch_num < len(batches):
            delay = weighted_delay(1.0, 3.0)
            log_info(f"Next batch in {delay:.1f}s...")
            await asyncio.sleep(delay)

    total = len(all_results)
    success = sum(1 for r in all_results if r.get("status") == "SUCCESS")
    failed = total - success

    log_info(f"\n{'='*60}")
    log_info(f"FINAL: {success}/{total} success, {failed} failed")
    log_info(f"{'='*60}")

    task_name = "Register + Say GM" if mode == "register_gm" else "Say GM"
    await send_telegram_summary(all_results, task_name)


async def main():
    mode = "gm_only" if len(sys.argv) > 1 and sys.argv[1] == "gm" else "register_gm"
    await run_all_batched(mode)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress saved.")
        sys.exit(0)
    except Exception as e:
        asyncio.run(alert_telegram(f"🚨 <b>[xStocks Bot] CRASHED!</b>\n{str(e)[:200]}"))
        raise
