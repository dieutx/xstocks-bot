"""Solana account signing helper."""

import base64 as _base64

import base58 as _base58
from solders.keypair import Keypair


class SolanaAccount:
    """Represents a single Solana account for message signing."""

    def __init__(self, index: int, private_key: str, proxy: str | None = None):
        self.index = index
        self.proxy = proxy
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
        """Sign a UTF-8 message with Ed25519 and return a base64 signature."""
        signature = self._keypair.sign_message(message.encode("utf-8"))
        return _base64.b64encode(bytes(signature)).decode()

    def __repr__(self) -> str:
        return (
            f"SolanaAccount(index={self.index}, "
            f"address={self.address[:10]}..., "
            f"proxy={'yes' if self.proxy else 'no'})"
        )
