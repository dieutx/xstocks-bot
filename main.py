"""
xStocks DeFi Bot — Entry point and parallel orchestrator.
Runs multiple accounts simultaneously as independent async tasks.
"""

import asyncio
import sys
import os
import random

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ACCOUNTS_FILE,
    PROXIES_FILE,
    ACCOUNT_START_DELAY_MIN,
    ACCOUNT_START_DELAY_MAX,
    MAX_STAGGER_WINDOW,
)
from core.account import BotAccount, load_accounts, load_all_accounts
from core.solana_account import SolanaAccount
from core.tasks import TASK_REGISTRY
from utils.proxy import load_proxies, pair_proxies_with_accounts
from utils.helpers import random_delay
from utils.logger import (
    log_info,
    log_error,
    log_success,
    log_warning,
    print_banner,
    print_summary,
)
from utils.telegram import send_telegram_summary


async def run_account_task(
    account: BotAccount,
    task_key: str,
) -> dict:
    """
    Run a task for a single account, catching all errors so other accounts
    are not affected.

    Args:
        account: The BotAccount to run.
        task_key: Key from TASK_REGISTRY.

    Returns:
        Result dict with index, address, status, details.
    """
    task_info = TASK_REGISTRY.get(task_key)
    if not task_info:
        return {
            "index": account.index,
            "address": account.address,
            "status": "FAILED",
            "details": f"Unknown task: {task_key}",
        }

    try:
        return await task_info["func"](account)
    except Exception as e:
        log_error(
            f"Fatal error in task '{task_key}': {e}",
            account.index,
            account.address,
        )
        return {
            "index": account.index,
            "address": account.address,
            "status": "FAILED",
            "details": f"Fatal: {str(e)[:80]}",
        }


async def run_all_accounts(
    accounts: list[BotAccount],
    task_key: str,
) -> list[dict]:
    """
    Run a task across all accounts in parallel with staggered starts.

    Args:
        accounts: List of BotAccount instances.
        task_key: Which task to run from TASK_REGISTRY.

    Returns:
        List of result dicts, one per account.
    """
    log_info(f"Starting task '{task_key}' for {len(accounts)} account(s)...")
    print()

    async def _staggered_run(account: BotAccount, delay: float) -> dict:
        if delay > 0:
            log_info(
                f"Waiting {delay:.1f}s before starting...",
                account.index,
                account.address,
            )
            await asyncio.sleep(delay)
        return await run_account_task(account, task_key)

    # Spread all accounts evenly across MAX_STAGGER_WINDOW seconds with slight jitter.
    # E.g. 100 accounts over 60s → ~0.6s step each, account 100 starts at ~60s.
    # This avoids the old formula where account 100 waited 300s+.
    n = len(accounts)
    window = max(ACCOUNT_START_DELAY_MIN, min(MAX_STAGGER_WINDOW, n * ACCOUNT_START_DELAY_MAX))
    step = window / max(n - 1, 1)

    tasks = []
    for i, account in enumerate(accounts):
        if i == 0:
            delay = 0.0
        else:
            jitter = random.uniform(-step * 0.2, step * 0.2)
            delay = round(i * step + jitter, 1)
            delay = max(0.0, delay)
        tasks.append(_staggered_run(account, delay))

    # Run all account tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results — handle any that raised exceptions
    processed: list[dict] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed.append({
                "index": accounts[i].index,
                "address": accounts[i].address,
                "status": "FAILED",
                "details": f"Exception: {str(result)[:80]}",
            })
        elif isinstance(result, dict):
            processed.append(result)
        else:
            processed.append({
                "index": accounts[i].index,
                "address": accounts[i].address,
                "status": "FAILED",
                "details": "Unknown result type",
            })

    return processed


def select_task() -> str:
    """Display task menu and get user selection."""
    print(f"\n{'=' * 50}")
    print("  Available Tasks:")
    print(f"{'=' * 50}")

    task_keys = list(TASK_REGISTRY.keys())
    for i, key in enumerate(task_keys, 1):
        info = TASK_REGISTRY[key]
        print(f"  {i}. {info['name']}")
        print(f"     {info['description']}")

    print(f"  {len(task_keys) + 1}. Exit")
    print(f"{'=' * 50}")

    while True:
        try:
            choice = input("\n  Select task (number): ").strip()
            if not choice:
                continue
            num = int(choice)
            if num == len(task_keys) + 1:
                print("\n  Exiting...")
                sys.exit(0)
            if 1 <= num <= len(task_keys):
                return task_keys[num - 1]
            print("  Invalid choice. Try again.")
        except ValueError:
            print("  Please enter a valid number.")
        except (KeyboardInterrupt, EOFError):
            print("\n  Exiting...")
            sys.exit(0)


async def main() -> None:
    """Main entry point: load accounts, select task, run in parallel."""
    print_banner()

    # Load proxies
    proxies = load_proxies(PROXIES_FILE)

    # Task selection first (determines which account file to load)
    task_key = select_task()
    task_info = TASK_REGISTRY[task_key]
    task_name = task_info["name"]
    wallet_type = task_info.get("wallet_type", "evm")

    # Load accounts based on wallet type
    paired = pair_proxies_with_accounts(100, proxies)
    try:
        if wallet_type == "mixed":
            # Auto-detect EVM/Solana from same file
            accounts = load_all_accounts(ACCOUNTS_FILE, paired)
        else:
            accounts = load_accounts(ACCOUNTS_FILE, paired)
    except (FileNotFoundError, ValueError) as e:
        log_error(f"Failed to load accounts: {e}")
        print(f"\n  Please add private keys to '{ACCOUNTS_FILE}' (one per line)")
        sys.exit(1)

    # Shuffle account order to avoid bot detection
    random.shuffle(accounts)
    for new_idx, acc in enumerate(accounts):
        acc.index = new_idx

    # Display account summary (shuffled order)
    print(f"\n  Loaded {len(accounts)} account(s) [order randomized]:")
    for acc in accounts:
        proxy_status = f"proxy: {acc._mask_proxy(acc.proxy)}" if acc.proxy else "no proxy"
        print(f"    Account {acc.index + 1}: {acc.address} ({proxy_status})")
    print()

    log_info(f"Selected task: {task_name}")

    # Run
    results = await run_all_accounts(accounts, task_key)

    # Print summary
    print_summary(results)

    # Send Telegram notification
    log_info("Sending Telegram summary...")
    sent = await send_telegram_summary(results, task_name)
    if sent:
        log_success("Telegram summary sent!")
    else:
        log_warning("Failed to send Telegram summary")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user. Exiting...")
        sys.exit(0)
