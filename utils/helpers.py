"""Key validation helpers."""


def is_valid_private_key(key: str) -> bool:
    """Validate that a string is a valid Ethereum private key."""
    key = key.strip()
    if key.startswith("0x"):
        key = key[2:]
    try:
        bytes.fromhex(key)
        return len(key) == 64
    except ValueError:
        return False


def is_valid_solana_key(key: str) -> bool:
    """Validate a base58-encoded Solana private key."""
    try:
        import base58 as _base58

        decoded = _base58.b58decode(key.strip())
        return len(decoded) in (32, 64)
    except Exception:
        return False


def detect_key_type(key: str) -> str | None:
    """Return 'evm', 'solana', or None for an unsupported key."""
    key = key.strip()
    if is_valid_private_key(key):
        return "evm"
    if is_valid_solana_key(key):
        return "solana"
    return None


def normalize_private_key(key: str) -> str:
    """Ensure an EVM private key has a 0x prefix."""
    key = key.strip()
    if not key.startswith("0x"):
        key = "0x" + key
    return key
