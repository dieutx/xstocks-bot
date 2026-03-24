"""
Generate wallets, import existing accounts, assign proxies, and save to accounts.json.

Usage:
    python generate_wallets.py                     # Generate + import + show stats
    python generate_wallets.py --proxies FILE      # Also assign proxies from file
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.db import (
    load_db,
    save_db,
    import_existing_accounts,
    generate_evm_wallets,
    generate_solana_wallets,
    assign_proxies,
    find_account,
)
from utils.logger import log_info, log_success, log_error, log_warning

NEW_EVM_COUNT = 854
NEW_SOLANA_COUNT = 238


def main():
    parser = argparse.ArgumentParser(description="Generate wallets and setup accounts.json")
    parser.add_argument("--proxies", help="Path to proxies file (one per line)")
    args = parser.parse_args()

    db = load_db()
    existing_addresses = {acc["address"].lower() for acc in db}

    # --- Step 1: Import existing accounts.txt if DB is empty ---
    if not db:
        accounts_file = "data/accounts.txt"
        proxies_file = "data/proxies.txt"

        if os.path.exists(accounts_file):
            log_info(f"Importing existing accounts from {accounts_file}...")
            imported = import_existing_accounts(accounts_file, proxies_file)
            db.extend(imported)
            existing_addresses = {acc["address"].lower() for acc in db}
            log_success(f"Imported {len(imported)} existing accounts with proxy pairings")
        else:
            log_warning("No existing accounts.txt found")

    evm_existing = sum(1 for a in db if a["wallet_type"] == "Evm")
    sol_existing = sum(1 for a in db if a["wallet_type"] == "Svm")
    log_info(f"Current DB: {len(db)} accounts ({evm_existing} EVM, {sol_existing} Solana)")

    # --- Step 2: Generate new EVM wallets ---
    new_evm_needed = NEW_EVM_COUNT
    log_info(f"Generating {new_evm_needed} new EVM wallets...")
    new_evm = generate_evm_wallets(new_evm_needed)

    # Deduplicate (extremely unlikely but safe)
    added_evm = 0
    for w in new_evm:
        if w["address"].lower() not in existing_addresses:
            db.append(w)
            existing_addresses.add(w["address"].lower())
            added_evm += 1
    log_success(f"Added {added_evm} new EVM wallets")

    # --- Step 3: Generate new Solana wallets ---
    new_sol_needed = NEW_SOLANA_COUNT
    log_info(f"Generating {new_sol_needed} new Solana wallets...")
    new_sol = generate_solana_wallets(new_sol_needed)

    added_sol = 0
    for w in new_sol:
        if w["address"].lower() not in existing_addresses:
            db.append(w)
            existing_addresses.add(w["address"].lower())
            added_sol += 1
    log_success(f"Added {added_sol} new Solana wallets")

    # --- Step 4: Assign proxies ---
    if args.proxies:
        log_info(f"Loading proxies from {args.proxies}...")
        with open(args.proxies) as f:
            proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        log_info(f"Loaded {len(proxies)} proxies")

        no_proxy = sum(1 for a in db if not a.get("proxy"))
        log_info(f"Accounts without proxy: {no_proxy}")

        assigned = assign_proxies(db, proxies)
        log_success(f"Assigned {assigned} new proxy pairings")

        still_no_proxy = sum(1 for a in db if not a.get("proxy"))
        if still_no_proxy:
            log_warning(f"{still_no_proxy} accounts still have no proxy (need more proxies)")
    else:
        no_proxy = sum(1 for a in db if not a.get("proxy"))
        if no_proxy:
            log_warning(f"{no_proxy} accounts have no proxy. Run with --proxies FILE to assign")

    # --- Step 5: Save ---
    save_db(db)

    # --- Summary ---
    total = len(db)
    evm_total = sum(1 for a in db if a["wallet_type"] == "Evm")
    sol_total = sum(1 for a in db if a["wallet_type"] == "Svm")
    registered = sum(1 for a in db if a.get("registered"))
    unregistered = total - registered
    with_proxy = sum(1 for a in db if a.get("proxy"))
    without_proxy = total - with_proxy

    print(f"\n{'='*50}")
    print(f"  ACCOUNTS DATABASE SUMMARY")
    print(f"{'='*50}")
    print(f"  Total accounts:    {total}")
    print(f"  EVM wallets:       {evm_total}")
    print(f"  Solana wallets:    {sol_total}")
    print(f"  Registered:        {registered}")
    print(f"  Unregistered:      {unregistered}")
    print(f"  With proxy:        {with_proxy}")
    print(f"  Without proxy:     {without_proxy}")
    print(f"{'='*50}")
    print(f"  Saved to: {os.path.abspath('data/accounts.json')}")
    print()


if __name__ == "__main__":
    main()
