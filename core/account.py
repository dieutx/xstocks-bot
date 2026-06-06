"""EVM account signing helper."""

from eth_account import Account as EthAccount
from eth_account.signers.local import LocalAccount

from utils.helpers import normalize_private_key


class BotAccount:
    """Represents a single EVM account for message signing."""

    def __init__(self, index: int, private_key: str, proxy: str | None = None):
        self.index: int = index
        self.private_key: str = normalize_private_key(private_key)
        self.proxy: str | None = proxy
        self._wallet: LocalAccount = EthAccount.from_key(self.private_key)
        self.address: str = self._wallet.address
        self.wallet_type: str = "Evm"

    @property
    def wallet(self) -> LocalAccount:
        return self._wallet

    def sign_message(self, message: str) -> str:
        """Sign a message and return a hex-encoded signature string."""
        from eth_account.messages import encode_defunct

        msg = encode_defunct(text=message)
        signed = self._wallet.sign_message(msg)
        return signed.signature.hex()

    def __repr__(self) -> str:
        return (
            f"BotAccount(index={self.index}, "
            f"address={self.address[:10]}..., "
            f"proxy={'yes' if self.proxy else 'no'})"
        )
