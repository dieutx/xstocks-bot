"""
SolanaAccount — Solana wallet with Ed25519 signing and proxy-aware HTTP session.
Same interface as BotAccount so it can be used interchangeably in tasks.
"""

import aiohttp
from aiohttp_socks import ProxyConnector

import base64 as _base64
import base58 as _base58
from solders.keypair import Keypair

from config import DEFAULT_HEADERS, REQUEST_TIMEOUT
from utils.logger import log_info, log_warning, log_error


class SolanaAccount:
    """Represents a single Solana bot account with wallet, proxy, and HTTP session."""

    def __init__(self, index: int, private_key: str, proxy: str | None = None):
        """
        Args:
            index: 0-based account index.
            private_key: Base58-encoded 64-byte Solana keypair (Phantom export format).
            proxy: Optional proxy URL (http/https/socks5).
        """
        self.index = index
        self.proxy = proxy
        self.auth_token: str | None = None
        self.session: aiohttp.ClientSession | None = None
        self.wallet_type: str = "Svm"

        key_bytes = _base58.b58decode(private_key.strip())
        if len(key_bytes) == 64:
            self._keypair = Keypair.from_bytes(key_bytes)
        elif len(key_bytes) == 32:
            self._keypair = Keypair.from_seed(key_bytes)
        else:
            raise ValueError(f"Invalid Solana key: expected 32 or 64 bytes, got {len(key_bytes)}")

        self.address: str = str(self._keypair.pubkey())

    def sign_message(self, message: str) -> str:
        """
        Sign a UTF-8 message with Ed25519 and return a base64-encoded signature.

        Args:
            message: The message string to sign.

        Returns:
            Base64-encoded signature string (required by Backed API for Solana).
        """
        msg_bytes = message.encode("utf-8")
        signature = self._keypair.sign_message(msg_bytes)
        return _base64.b64encode(bytes(signature)).decode()

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
            f"SolanaAccount(index={self.index}, "
            f"address={self.address[:10]}..., "
            f"proxy={'yes' if self.proxy else 'no'})"
        )


def load_solana_accounts(
    accounts_file: str, proxies: list[str | None]
) -> list[SolanaAccount]:
    """
    Load Solana accounts from file and pair with proxies.

    Args:
        accounts_file: Path to file with one base58 private key per line.
        proxies: List of proxy URLs (or None), aligned by index.

    Returns:
        List of SolanaAccount instances.
    """
    import os
    from utils.helpers import is_valid_solana_key
    from utils.logger import log_warning, log_error

    if not os.path.exists(accounts_file):
        log_error(f"Solana accounts file not found: {accounts_file}")
        raise FileNotFoundError(f"Solana accounts file not found: {accounts_file}")

    accounts: list[SolanaAccount] = []
    with open(accounts_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            key = line.strip()
            if not key or key.startswith("#"):
                continue

            if not is_valid_solana_key(key):
                log_warning(f"Skipping invalid Solana key on line {i + 1}")
                continue

            proxy = proxies[len(accounts)] if len(accounts) < len(proxies) else None
            accounts.append(SolanaAccount(index=len(accounts), private_key=key, proxy=proxy))

    if not accounts:
        log_error("No valid Solana accounts found")
        raise ValueError("No valid Solana accounts found")

    log_info(f"Loaded {len(accounts)} Solana account(s)")
    return accounts
