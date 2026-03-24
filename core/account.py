"""
Account class — encapsulates a wallet (private key), its proxy, and its HTTP session.
Each account is an independent unit that can run tasks in parallel.
"""

import os
import ssl

import aiohttp
from aiohttp_socks import ProxyConnector
from eth_account import Account as EthAccount
from eth_account.signers.local import LocalAccount

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from utils.helpers import normalize_private_key, is_valid_private_key, detect_key_type
from utils.logger import log_info, log_warning, log_error


class BotAccount:
    """Represents a single bot account with wallet, proxy, and HTTP session."""

    def __init__(self, index: int, private_key: str, proxy: str | None = None):
        """
        Args:
            index: 0-based account index.
            private_key: Ethereum private key (hex string).
            proxy: Optional proxy URL (http/https/socks5).
        """
        self.index: int = index
        self.private_key: str = normalize_private_key(private_key)
        self.proxy: str | None = proxy
        self._wallet: LocalAccount = EthAccount.from_key(self.private_key)
        self.address: str = self._wallet.address
        self.session: aiohttp.ClientSession | None = None
        self.auth_token: str | None = None
        self.wallet_type: str = "Evm"

    @property
    def wallet(self) -> LocalAccount:
        return self._wallet

    async def create_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session with the assigned proxy (if any)."""
        connector: aiohttp.BaseConnector | None = None

        if self.proxy:
            try:
                connector = ProxyConnector.from_url(self.proxy)
                log_info(
                    f"Using proxy: {self._mask_proxy(self.proxy)}",
                    self.index,
                    self.address,
                )
            except Exception as e:
                log_warning(
                    f"Failed to set up proxy ({e}). Continuing without proxy.",
                    self.index,
                    self.address,
                )
                connector = None
        else:
            log_info("No proxy assigned", self.index, self.address)

        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=DEFAULT_HEADERS.copy(),
        )
        return self.session

    async def close_session(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def sign_message(self, message: str) -> str:
        """
        Sign a message with the account's private key.

        Args:
            message: The message string to sign.

        Returns:
            Hex-encoded signature string.
        """
        from eth_account.messages import encode_defunct

        msg = encode_defunct(text=message)
        signed = self._wallet.sign_message(msg)
        return signed.signature.hex()

    def _mask_proxy(self, proxy: str) -> str:
        """Mask credentials in proxy URL for logging."""
        try:
            if "@" in proxy:
                scheme_and_creds, host = proxy.rsplit("@", 1)
                scheme = scheme_and_creds.split("://")[0]
                return f"{scheme}://****@{host}"
        except Exception:
            pass
        return proxy

    def __repr__(self) -> str:
        return (
            f"BotAccount(index={self.index}, "
            f"address={self.address[:10]}..., "
            f"proxy={'yes' if self.proxy else 'no'})"
        )


def load_accounts(
    accounts_file: str, proxies: list[str | None]
) -> list[BotAccount]:
    """
    Load accounts from file and pair with proxies.

    Args:
        accounts_file: Path to accounts.txt with one private key per line.
        proxies: List of proxy URLs (or None), aligned by index.

    Returns:
        List of BotAccount instances.
    """
    if not os.path.exists(accounts_file):
        log_error(f"Accounts file not found: {accounts_file}")
        raise FileNotFoundError(f"Accounts file not found: {accounts_file}")

    accounts: list[BotAccount] = []
    with open(accounts_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            key = line.strip()
            if not key or key.startswith("#"):
                continue

            if not is_valid_private_key(key):
                log_warning(f"Skipping invalid private key on line {i + 1}")
                continue

            proxy = proxies[len(accounts)] if len(accounts) < len(proxies) else None
            account = BotAccount(index=len(accounts), private_key=key, proxy=proxy)
            accounts.append(account)

    if not accounts:
        log_error("No valid accounts found in accounts file")
        raise ValueError("No valid accounts found")

    log_info(f"Loaded {len(accounts)} account(s)")
    return accounts


def load_all_accounts(
    accounts_file: str, proxies: list[str | None]
) -> list:
    """
    Load EVM and Solana accounts from the same file, auto-detecting key type per line.
    EVM keys: 64 hex chars (with or without 0x prefix).
    Solana keys: base58-encoded 32-byte seed or 64-byte keypair.

    Args:
        accounts_file: Path to accounts.txt with one private key per line.
        proxies: List of proxy URLs (or None), aligned by index.

    Returns:
        List of BotAccount or SolanaAccount instances.
    """
    # Import here to avoid circular imports
    from core.solana_account import SolanaAccount

    if not os.path.exists(accounts_file):
        log_error(f"Accounts file not found: {accounts_file}")
        raise FileNotFoundError(f"Accounts file not found: {accounts_file}")

    accounts: list = []
    evm_count = 0
    solana_count = 0

    with open(accounts_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            key = line.strip()
            if not key or key.startswith("#"):
                continue

            key_type = detect_key_type(key)
            if key_type is None:
                log_warning(f"Skipping unrecognized key on line {i + 1}")
                continue

            proxy = proxies[len(accounts)] if len(accounts) < len(proxies) else None

            if key_type == "evm":
                accounts.append(BotAccount(index=len(accounts), private_key=key, proxy=proxy))
                evm_count += 1
            else:
                accounts.append(SolanaAccount(index=len(accounts), private_key=key, proxy=proxy))
                solana_count += 1

    if not accounts:
        log_error("No valid accounts found in accounts file")
        raise ValueError("No valid accounts found")

    log_info(f"Loaded {len(accounts)} account(s): {evm_count} EVM, {solana_count} Solana")
    return accounts
