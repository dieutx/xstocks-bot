"""
Task definitions — each task is an async function that takes a BotAccount
and performs a specific action (login, Say GM checkin, etc.).
"""

import asyncio

from core.account import BotAccount, load_all_accounts
from core.solana_account import SolanaAccount
from core.api import (
    login,
    say_gm,
    get_user_info,
    get_points,
    get_dashboard,
    backed_say_gm,
    daily_spin_multiplier,
    register_user,
    get_xdrop_user,
    resolve_proxy_ip,
    _NOT_FOUND,
)
from utils.helpers import random_delay
from utils.logger import log_info, log_success, log_error, log_warning
from config import TASK_DELAY_MIN, TASK_DELAY_MAX, REGISTER_DELAY_MIN, REGISTER_DELAY_MAX


async def task_say_gm(account: BotAccount) -> dict:
    """
    Complete flow for the daily "Say GM" task:
    1. Create HTTP session
    2. Authenticate via SIWE
    3. Perform Say GM checkin
    4. Fetch points balance
    5. Close session

    Args:
        account: BotAccount to run the task for.

    Returns:
        Result dict with keys: index, address, status, details.
    """
    result = {
        "index": account.index,
        "address": account.address,
        "status": "FAILED",
        "details": "",
    }

    try:
        # Step 1: Create session
        log_info("Starting Say GM task...", account.index, account.address)
        await account.create_session()

        # Step 2: Authenticate
        log_info("Authenticating...", account.index, account.address)
        auth_ok = await login(account)
        if not auth_ok:
            result["details"] = "Authentication failed"
            log_error("Authentication failed", account.index, account.address)
            return result

        await random_delay(TASK_DELAY_MIN, TASK_DELAY_MAX)

        # Step 3: Say GM checkin
        gm_ok = await say_gm(account)
        if not gm_ok:
            result["details"] = "Say GM failed"
            log_error("Say GM checkin failed", account.index, account.address)
            return result

        await random_delay(TASK_DELAY_MIN, TASK_DELAY_MAX)

        # Step 4: Fetch points (optional, don't fail on this)
        try:
            points_data = await get_points(account)
            if points_data:
                total = (
                    points_data.get("total")
                    or points_data.get("points")
                    or points_data.get("balance")
                    or "N/A"
                )
                result["details"] = f"Points: {total}"
            else:
                result["details"] = "GM done (points unknown)"
        except Exception:
            result["details"] = "GM done"

        result["status"] = "SUCCESS"
        log_success(
            f"Say GM task completed! {result['details']}",
            account.index,
            account.address,
        )
        return result

    except Exception as e:
        result["details"] = f"Error: {str(e)[:80]}"
        log_error(
            f"Say GM task error: {e}",
            account.index,
            account.address,
        )
        return result

    finally:
        await account.close_session()


async def task_full_daily(account: BotAccount) -> dict:
    """
    Run all daily tasks for an account:
    1. Authenticate
    2. Fetch dashboard → get gmClicksRemaining
    3. Say GM N times (backed_say_gm)
    4. Daily spin multiplier (if not yet revealed)

    Args:
        account: BotAccount to run tasks for.

    Returns:
        Result dict with keys: index, address, status, details.
    """
    result = {
        "index": account.index,
        "address": account.address,
        "status": "FAILED",
        "details": "",
    }

    try:
        await account.create_session()

        # Resolve proxy IP
        proxy_ip = await resolve_proxy_ip(account)
        if proxy_ip:
            log_info(f"Proxy IP: {proxy_ip}", account.index, account.address)

        # Step 1: Authenticate
        log_info("Authenticating...", account.index, account.address)
        auth_ok = await login(account)
        if not auth_ok:
            result["details"] = "Authentication failed"
            log_error("Authentication failed", account.index, account.address)
            return result

        await random_delay(TASK_DELAY_MIN, TASK_DELAY_MAX)

        # Step 2: Fetch dashboard
        dashboard = await get_dashboard(account)
        if dashboard:
            gm_clicks = int(dashboard.get("gmClicksRemaining") or 0)
            spin_revealed = dashboard.get("dailySpinMultiplierRevealed", True)
            total_points = dashboard.get("totalPoints", "?")
            log_info(
                f"Dashboard | Points: {total_points} | GM clicks remaining: {gm_clicks} | "
                f"Spin multiplier revealed: {spin_revealed}",
                account.index,
                account.address,
            )
        else:
            log_warning("Could not fetch dashboard, proceeding with defaults", account.index, account.address)
            gm_clicks = 1
            spin_revealed = True
            total_points = "?"

        await random_delay(TASK_DELAY_MIN, TASK_DELAY_MAX)

        # Step 3: Say GM (backed) — loops until clicksRemaining=0
        gm_done = await backed_say_gm(account)

        await random_delay(TASK_DELAY_MIN, TASK_DELAY_MAX)

        # Step 4: Daily spin multiplier — only if not yet revealed today
        spin_done = False
        if not spin_revealed:
            spin_done = await daily_spin_multiplier(account)
        else:
            log_info("Daily spin multiplier already revealed, skipping", account.index, account.address)

        # Build summary
        parts = [f"GM: {gm_done} click(s)"]
        if not spin_revealed:
            parts.append(f"Spin: {'done' if spin_done else 'failed'}")
        if dashboard:
            parts.append(f"Points: {total_points}")
        result["details"] = " | ".join(parts)
        result["status"] = "SUCCESS"
        log_success(
            f"Full daily completed! {result['details']}",
            account.index,
            account.address,
        )
        return result

    except Exception as e:
        result["details"] = f"Error: {str(e)[:80]}"
        log_error(f"Full daily task error: {e}", account.index, account.address)
        return result

    finally:
        await account.close_session()


async def task_register_and_gm(account: "BotAccount | SolanaAccount") -> dict:
    """
    Smart register + Say GM flow:
        1. Open HTTP session (with proxy)
        2. Resolve proxy IP and log it
        3. Check if account already exists (GET /xdrop-user/{wallet})
        4. If not exists → register
        5. Check dashboard for gmClicksRemaining
        6. If gmClicksRemaining > 0 → Say GM, else skip

    Args:
        account: BotAccount (EVM) or SolanaAccount to register and run GM for.

    Returns:
        Result dict with keys: index, address, status, details.
    """
    result = {
        "index": account.index,
        "address": account.address,
        "status": "FAILED",
        "details": "",
    }

    try:
        await account.create_session()

        # Step 0: Resolve and log proxy IP
        proxy_ip = await resolve_proxy_ip(account)
        if proxy_ip:
            log_info(f"Proxy IP: {proxy_ip}", account.index, account.address)
        elif account.proxy:
            log_warning("Could not resolve proxy IP", account.index, account.address)

        # Step 1: Check if account already exists
        log_info("Checking if account exists...", account.index, account.address)
        user_data = await get_xdrop_user(account)

        is_new = False
        if user_data is _NOT_FOUND:
            # Definitively not registered → register
            is_new = True
            log_info(f"Account not found, registering {account.wallet_type}...", account.index, account.address)
            registered = await register_user(account)
            if not registered:
                result["details"] = "Registration failed"
                log_error("Registration failed, skipping GM", account.index, account.address)
                return result

            # Human-like pause after registration
            delay = await random_delay(REGISTER_DELAY_MIN, REGISTER_DELAY_MAX)
            log_info(f"Registered! Waiting {delay:.1f}s before dashboard check...", account.index, account.address)
        elif user_data is None:
            # Check failed (timeout) — skip registration to avoid "already exists" noise
            log_warning("Could not verify account status (timeout), skipping registration", account.index, account.address)
        else:
            log_info("Account already registered, skipping registration", account.index, account.address)

        # Step 3: Check dashboard for gmClicksRemaining
        log_info("Checking dashboard for GM clicks...", account.index, account.address)
        dashboard = await get_dashboard(account)

        if dashboard:
            gm_remaining = int(dashboard.get("gmClicksRemaining", 0))
            total_points = dashboard.get("totalPoints", "?")
            today_points = dashboard.get("todayPoints", "?")
            log_info(
                f"Dashboard | Points: {total_points} | Today: {today_points} | GM remaining: {gm_remaining}",
                account.index,
                account.address,
            )
        else:
            # Dashboard failed — only attempt GM for newly registered accounts
            if is_new:
                log_warning("Could not fetch dashboard, attempting GM for new account", account.index, account.address)
                gm_remaining = 1
            else:
                log_warning("Could not fetch dashboard, skipping GM to avoid duplicate click", account.index, account.address)
                gm_remaining = 0

        # Step 4: Say GM if clicks remaining
        if gm_remaining > 0:
            gm_done = await backed_say_gm(account)
        else:
            gm_done = 0
            log_info("GM clicks remaining: 0 → skipping Say GM", account.index, account.address)

        status_parts = []
        if user_data and user_data is not _NOT_FOUND:
            status_parts.append("Existing")
        else:
            status_parts.append(f"Registered ({account.wallet_type})")
        status_parts.append(f"GM: {gm_done} click(s)")
        if proxy_ip:
            status_parts.append(f"IP: {proxy_ip}")

        result["status"] = "SUCCESS"
        result["details"] = " | ".join(status_parts)
        log_success(
            f"Register + GM completed! {result['details']}",
            account.index,
            account.address,
        )
        return result

    except Exception as e:
        err_msg = str(e) or f"{type(e).__name__} (no message)"
        result["details"] = f"Error: {err_msg[:80]}"
        log_error(f"Register+GM task error: {err_msg}", account.index, account.address)
        return result

    finally:
        await account.close_session()


async def task_backed_say_gm(account: BotAccount) -> dict:
    """
    Perform Say GM for an already-registered account (no registration step).
    Checks dashboard first to see if GM clicks are available.

    Args:
        account: BotAccount to run GM for.

    Returns:
        Result dict with keys: index, address, status, details.
    """
    result = {
        "index": account.index,
        "address": account.address,
        "status": "FAILED",
        "details": "",
    }

    try:
        await account.create_session()

        # Resolve proxy IP
        proxy_ip = await resolve_proxy_ip(account)
        if proxy_ip:
            log_info(f"Proxy IP: {proxy_ip}", account.index, account.address)

        # Check dashboard for gmClicksRemaining
        dashboard = await get_dashboard(account)
        if dashboard:
            gm_remaining = int(dashboard.get("gmClicksRemaining", 0))
            total_points = dashboard.get("totalPoints", "?")
            log_info(f"GM clicks remaining: {gm_remaining} | Points: {total_points}", account.index, account.address)
            if gm_remaining == 0:
                result["status"] = "SUCCESS"
                result["details"] = f"GM: already done | Points: {total_points}"
                if proxy_ip:
                    result["details"] += f" | IP: {proxy_ip}"
                log_info("GM clicks remaining: 0 → skipping", account.index, account.address)
                return result
        else:
            # Dashboard failed — don't blindly attempt GM, it may already be done
            log_warning("Could not fetch dashboard, skipping GM to avoid duplicate click", account.index, account.address)
            result["status"] = "FAILED"
            result["details"] = "Dashboard check failed"
            if proxy_ip:
                result["details"] += f" | IP: {proxy_ip}"
            return result

        # Dashboard confirmed clicks remaining > 0, proceed with GM
        gm_done = await backed_say_gm(account)

        # backed_say_gm already checks dashboard on error internally,
        # so gm_done == 0 here means GM was confirmed done (not a failure)
        result["status"] = "SUCCESS"
        if gm_done > 0:
            result["details"] = f"GM: {gm_done} click(s)"
        else:
            result["details"] = "GM: already done"

        if proxy_ip:
            result["details"] += f" | IP: {proxy_ip}"
        return result

    except Exception as e:
        err_msg = str(e) or f"{type(e).__name__} (no message)"
        result["details"] = f"Error: {err_msg[:80]}"
        log_error(f"Backed Say GM task error: {err_msg}", account.index, account.address)
        return result

    finally:
        await account.close_session()




# Registry of available tasks
TASK_REGISTRY: dict[str, dict] = {
    "register_and_gm": {
        "name": "Register + Say GM",
        "description": "Register EVM/Solana wallets from accounts.txt with referral code, then Say GM",
        "func": task_register_and_gm,
        "wallet_type": "mixed",
    },
    "backed_say_gm": {
        "name": "Say GM (Backed API)",
        "description": "Say GM for existing accounts via Backed API until all clicks used",
        "func": task_backed_say_gm,
    },
    "full_daily": {
        "name": "Full Daily Routine",
        "description": "Run all daily tasks (SIWE login + GM + spin)",
        "func": task_full_daily,
    },
}
