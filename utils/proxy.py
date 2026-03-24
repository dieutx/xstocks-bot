"""
Proxy manager — loads proxies from file, validates format, pairs with accounts.
Supports http://, https://, socks5:// proxy formats.
"""

import os

from utils.logger import log_info, log_warning

from config import PROXIES_FILE


def load_proxies(file_path: str = PROXIES_FILE) -> list[str | None]:
    """
    Load proxy list from file. One proxy per line.
    Supported formats: http://user:pass@host:port, socks5://user:pass@host:port

    Returns:
        List of proxy URL strings (or empty list if file missing).
    """
    if not os.path.exists(file_path):
        log_warning(f"Proxy file not found: {file_path}. Running without proxies.")
        return []

    proxies: list[str | None] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if _validate_proxy(line):
                proxies.append(line)
            else:
                log_warning(f"Invalid proxy format on line {i}: {line}")

    log_info(f"Loaded {len(proxies)} proxies from {file_path}")
    return proxies


def _validate_proxy(proxy: str) -> bool:
    """Check if proxy string has a valid format."""
    valid_schemes = ("http://", "https://", "socks5://", "socks4://")
    return any(proxy.lower().startswith(scheme) for scheme in valid_schemes)


def pair_proxies_with_accounts(
    account_count: int, proxies: list[str | None]
) -> list[str | None]:
    """
    Match proxies 1:1 with accounts by line number.
    If fewer proxies than accounts, remaining accounts get None (no proxy).

    Args:
        account_count: Number of accounts loaded.
        proxies: List of proxy URLs.

    Returns:
        List of proxy URLs (or None) aligned with account indices.
    """
    paired: list[str | None] = []
    for i in range(account_count):
        if i < len(proxies):
            paired.append(proxies[i])
        else:
            paired.append(None)

    if len(proxies) < account_count:
        diff = account_count - len(proxies)
        log_warning(
            f"{diff} account(s) will run without proxy "
            f"({len(proxies)} proxies for {account_count} accounts)"
        )

    return paired
