"""
Utility functions: retry with exponential backoff, random delays, key validation.
"""

import asyncio
import random
from typing import Any, Callable, Coroutine

from config import MAX_RETRIES, RETRY_BASE_DELAY, RATE_LIMIT_DELAY
from utils.logger import log_warning, log_error, log_info


async def retry_async(
    func: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
    account_index: int | None = None,
    address: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async callable to retry.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay for exponential backoff (seconds).
        account_index: For logging context.
        address: For logging context.

    Returns:
        The result of the function call.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except RateLimitError:
            log_warning(
                f"Rate limited (429). Waiting {RATE_LIMIT_DELAY}s before retry...",
                account_index,
                address,
            )
            await asyncio.sleep(RATE_LIMIT_DELAY)
            last_exception = RateLimitError("Rate limited")
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                err_msg = str(e) or f"{type(e).__name__} (no message)"
                log_warning(
                    f"Attempt {attempt}/{max_retries} failed: {err_msg}. "
                    f"Retrying in {delay:.1f}s...",
                    account_index,
                    address,
                )
                await asyncio.sleep(delay)
            else:
                err_msg = str(e) or f"{type(e).__name__} (no message)"
                log_error(
                    f"All {max_retries} attempts failed. Last error: {err_msg}",
                    account_index,
                    address,
                )

    if last_exception:
        # Wrap exceptions with empty messages so callers get useful info
        if not str(last_exception):
            raise type(last_exception)(
                f"{type(last_exception).__name__} (proxy/connection error)"
            ) from last_exception
        raise last_exception
    raise RuntimeError("Unexpected: no result and no exception after retries")


class RateLimitError(Exception):
    """Raised when an HTTP 429 response is received."""
    pass


async def random_delay(min_sec: float, max_sec: float) -> float:
    """Sleep for a random duration between min_sec and max_sec. Returns actual delay."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)
    return delay


def is_valid_private_key(key: str) -> bool:
    """Validate that a string is a valid Ethereum private key (64 hex chars)."""
    key = key.strip()
    if key.startswith("0x"):
        key = key[2:]
    try:
        bytes.fromhex(key)
        return len(key) == 64
    except ValueError:
        return False


def is_valid_solana_key(key: str) -> bool:
    """Validate a base58-encoded Solana private key (32-byte seed or 64-byte keypair)."""
    try:
        import base58 as _base58
        decoded = _base58.b58decode(key.strip())
        return len(decoded) in (32, 64)
    except Exception:
        return False


def detect_key_type(key: str) -> str | None:
    """
    Detect whether a private key is EVM or Solana.

    Returns:
        'evm', 'solana', or None if invalid.
    """
    key = key.strip()
    if is_valid_private_key(key):
        return "evm"
    if is_valid_solana_key(key):
        return "solana"
    return None


def normalize_private_key(key: str) -> str:
    """Ensure private key has 0x prefix."""
    key = key.strip()
    if not key.startswith("0x"):
        key = "0x" + key
    return key


def short_address(address: str) -> str:
    """Shorten an Ethereum address: 0xAbC...xYz."""
    if len(address) >= 10:
        return f"{address[:6]}...{address[-4:]}"
    return address
