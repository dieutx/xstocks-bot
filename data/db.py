"""
Persistent account-proxy database.
Stores wallet info, proxy assignment, and registration/GM status in a JSON file.
Account-proxy pairing is permanent and never changes once assigned.
"""

import json
import os
import random
from datetime import datetime
from pathlib import Path

DB_FILE = Path(__file__).parent / "accounts.json"


def load_db() -> list[dict]:
    """Load the accounts database. Returns empty list if file doesn't exist."""
    if not DB_FILE.exists():
        return []
    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_db(accounts: list[dict]) -> None:
    """Save the accounts database atomically."""
    tmp = str(DB_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(accounts, f, indent=2)
    os.replace(tmp, str(DB_FILE))


def find_account(db: list[dict], address: str) -> dict | None:
    """Find an account by wallet address (case-insensitive for EVM)."""
    addr_lower = address.lower()
    for acc in db:
        if acc["address"].lower() == addr_lower:
            return acc
    return None


def import_existing_accounts(
    accounts_file: str,
    proxies_file: str,
) -> list[dict]:
    """
    Import existing accounts.txt + proxies.txt into DB format.
    Preserves 1:1 pairing by line number.

    Returns:
        List of account dicts ready for DB.
    """
    from utils.helpers import detect_key_type

    with open(accounts_file) as f:
        keys = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    with open(proxies_file) as f:
        proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    accounts = []
    for i, key in enumerate(keys):
        proxy = proxies[i] if i < len(proxies) else None
        key_type = detect_key_type(key)

        # Derive address
        if key_type == "evm":
            from eth_account import Account as EthAccount
            pk = key if key.startswith("0x") else f"0x{key}"
            address = EthAccount.from_key(pk).address
            wallet_type = "Evm"
        elif key_type == "solana":
            import base58
            from solders.keypair import Keypair
            key_bytes = base58.b58decode(key)
            if len(key_bytes) == 64:
                kp = Keypair.from_bytes(key_bytes)
            else:
                kp = Keypair.from_seed(key_bytes)
            address = str(kp.pubkey())
            wallet_type = "Svm"
        else:
            continue

        accounts.append({
            "private_key": key,
            "address": address,
            "wallet_type": wallet_type,
            "proxy": proxy,
            "registered": True,  # existing accounts are already registered
            "gm_last_date": None,
            "created_at": datetime.now().isoformat(),
        })

    return accounts


def generate_evm_wallets(count: int) -> list[dict]:
    """Generate new random EVM wallets."""
    from eth_account import Account as EthAccount

    wallets = []
    for _ in range(count):
        acct = EthAccount.create()
        wallets.append({
            "private_key": acct.key.hex(),
            "address": acct.address,
            "wallet_type": "Evm",
            "proxy": None,
            "registered": False,
            "gm_last_date": None,
            "created_at": datetime.now().isoformat(),
        })
    return wallets


def generate_solana_wallets(count: int) -> list[dict]:
    """Generate new random Solana wallets."""
    import base64 as _base64
    from solders.keypair import Keypair
    import base58

    wallets = []
    for _ in range(count):
        kp = Keypair()
        wallets.append({
            "private_key": base58.b58encode(bytes(kp)).decode(),
            "address": str(kp.pubkey()),
            "wallet_type": "Svm",
            "proxy": None,
            "registered": False,
            "gm_last_date": None,
            "created_at": datetime.now().isoformat(),
        })
    return wallets


def assign_proxies(accounts: list[dict], proxies: list[str]) -> int:
    """
    Assign proxies to accounts that don't have one yet.
    Each proxy is used exactly once. Pairing is permanent.

    Args:
        accounts: List of account dicts (modified in place).
        proxies: List of available proxy URLs.

    Returns:
        Number of proxies assigned.
    """
    # Collect already-used proxies
    used_proxies = {acc["proxy"] for acc in accounts if acc["proxy"]}

    # Available proxies (not yet assigned)
    available = [p for p in proxies if p not in used_proxies]

    assigned = 0
    for acc in accounts:
        if acc["proxy"] is None and available:
            acc["proxy"] = available.pop(0)
            assigned += 1

    return assigned


def get_accounts_needing_registration(db: list[dict]) -> list[dict]:
    """Get accounts that haven't been registered yet."""
    return [acc for acc in db if not acc.get("registered")]


def get_accounts_needing_gm(db: list[dict], date_str: str | None = None) -> list[dict]:
    """Get accounts that haven't done GM today."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return [acc for acc in db if acc.get("gm_last_date") != date_str]


def mark_registered(db: list[dict], address: str) -> None:
    """Mark an account as registered."""
    acc = find_account(db, address)
    if acc:
        acc["registered"] = True


def mark_gm_done(db: list[dict], address: str) -> None:
    """Mark an account's GM as done for today."""
    acc = find_account(db, address)
    if acc:
        acc["gm_last_date"] = datetime.now().strftime("%Y-%m-%d")


def make_batches(
    accounts: list[dict],
    min_size: int = 6,
    max_size: int = 13,
) -> list[list[dict]]:
    """
    Split accounts into randomized batches of mixed EVM/Solana.
    Each batch has 6-13 accounts with a mix of both types.

    Args:
        accounts: List of account dicts to batch.
        min_size: Minimum batch size.
        max_size: Maximum batch size.

    Returns:
        List of batches, each batch is a list of account dicts.
    """
    # Separate by type and shuffle each
    evm = [a for a in accounts if a["wallet_type"] == "Evm"]
    sol = [a for a in accounts if a["wallet_type"] == "Svm"]
    random.shuffle(evm)
    random.shuffle(sol)

    # Interleave to ensure mix in each batch
    total = len(evm) + len(sol)
    if total == 0:
        return []

    # Calculate ratio for mixing
    interleaved = []
    ei, si = 0, 0
    while ei < len(evm) or si < len(sol):
        # Add accounts proportionally
        if ei < len(evm) and (si >= len(sol) or random.random() < len(evm) / total):
            interleaved.append(evm[ei])
            ei += 1
        elif si < len(sol):
            interleaved.append(sol[si])
            si += 1

    # Split into batches
    batches = []
    idx = 0
    while idx < len(interleaved):
        batch_size = random.randint(min_size, max_size)
        batch = interleaved[idx:idx + batch_size]
        if batch:
            batches.append(batch)
        idx += batch_size

    return batches
