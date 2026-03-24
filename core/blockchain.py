"""
On-chain interactions using web3.py.
Handles RPC connection, balance checks, and transaction signing/sending.
"""

import asyncio
import random
from typing import Any

from web3 import Web3
from web3.exceptions import ContractLogicError
from eth_account import Account as EthAccount

from config import RPC_URLS, CHAIN_ID, EXPLORER_URL
from core.account import BotAccount
from utils.logger import log_info, log_success, log_error, log_warning


def connect_web3(rpc_urls: list[str] | None = None) -> Web3:
    """
    Connect to an EVM RPC endpoint. Tries multiple URLs.

    Args:
        rpc_urls: List of RPC URLs to try. Defaults to config.

    Returns:
        Connected Web3 instance.

    Raises:
        ConnectionError if no RPC can be connected.
    """
    urls = rpc_urls or RPC_URLS
    for url in urls:
        try:
            w3 = Web3(Web3.HTTPProvider(url))
            if w3.is_connected():
                chain_id = w3.eth.chain_id
                log_info(f"Connected to RPC: {url} | Chain ID: {chain_id}")
                return w3
        except Exception as e:
            log_warning(f"Failed to connect to RPC {url}: {e}")

    raise ConnectionError(f"Could not connect to any RPC endpoint: {urls}")


async def get_balance(w3: Web3, address: str) -> float:
    """Get ETH balance for an address in ether units."""
    balance_wei = await asyncio.get_event_loop().run_in_executor(
        None, w3.eth.get_balance, address
    )
    return float(w3.from_wei(balance_wei, "ether"))


async def send_transaction(
    w3: Web3,
    account: BotAccount,
    to_address: str,
    value_ether: float = 0.0,
    data: bytes = b"",
) -> str | None:
    """
    Build, sign, and send a transaction.

    Args:
        w3: Connected Web3 instance.
        account: BotAccount with private key.
        to_address: Destination address.
        value_ether: Value to send in ether.
        data: Transaction data (for contract calls).

    Returns:
        Transaction hash hex string, or None on failure.
    """
    loop = asyncio.get_event_loop()
    sender = account.address

    try:
        nonce = await loop.run_in_executor(
            None, w3.eth.get_transaction_count, sender
        )
        gas_price = await loop.run_in_executor(None, lambda: w3.eth.gas_price)
        gas_price = int(gas_price * 1.2)  # 20% buffer

        tx: dict[str, Any] = {
            "nonce": nonce,
            "to": Web3.to_checksum_address(to_address),
            "value": w3.to_wei(value_ether, "ether"),
            "gasPrice": gas_price,
            "chainId": CHAIN_ID,
        }

        if data:
            tx["data"] = data

        # Estimate gas
        try:
            estimated_gas = await loop.run_in_executor(
                None, w3.eth.estimate_gas, tx
            )
            tx["gas"] = int(estimated_gas * 1.2)
        except Exception:
            tx["gas"] = 21000 if not data else 200000

        # Check balance
        balance = await get_balance(w3, sender)
        required = float(w3.from_wei(tx["gas"] * gas_price + tx["value"], "ether"))
        if balance < required:
            log_error(
                f"Insufficient balance: {balance:.6f} (need {required:.6f})",
                account.index,
                account.address,
            )
            return None

        # Sign and send
        signed = w3.eth.account.sign_transaction(tx, account.private_key)
        tx_hash = await loop.run_in_executor(
            None, w3.eth.send_raw_transaction, signed.raw_transaction
        )

        tx_hex = tx_hash.hex()
        log_info(
            f"Tx sent: {EXPLORER_URL}{tx_hex}",
            account.index,
            account.address,
        )

        # Wait for receipt
        receipt = await loop.run_in_executor(
            None, lambda: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        )

        if receipt.status == 1:
            log_success(
                f"Tx confirmed in block {receipt['blockNumber']} | "
                f"Gas used: {receipt['gasUsed']}",
                account.index,
                account.address,
            )
            return tx_hex
        else:
            log_error(
                f"Tx reverted: {EXPLORER_URL}{tx_hex}",
                account.index,
                account.address,
            )
            return None

    except Exception as e:
        log_error(f"Transaction failed: {e}", account.index, account.address)
        return None


async def call_contract(
    w3: Web3,
    account: BotAccount,
    contract_address: str,
    abi: list[dict],
    function_name: str,
    *args: Any,
    value_ether: float = 0.0,
) -> str | None:
    """
    Call a smart contract function (state-changing).

    Args:
        w3: Connected Web3 instance.
        account: BotAccount with private key.
        contract_address: Contract address.
        abi: Contract ABI.
        function_name: Name of the function to call.
        *args: Function arguments.
        value_ether: ETH value to send with the call.

    Returns:
        Transaction hash hex string, or None on failure.
    """
    loop = asyncio.get_event_loop()

    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), abi=abi
        )
        func = contract.functions[function_name](*args)

        nonce = await loop.run_in_executor(
            None, w3.eth.get_transaction_count, account.address
        )
        gas_price = await loop.run_in_executor(None, lambda: w3.eth.gas_price)
        gas_price = int(gas_price * 1.2)

        tx = func.build_transaction({
            "from": account.address,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gasPrice": gas_price,
            "value": w3.to_wei(value_ether, "ether"),
        })

        # Estimate gas
        try:
            estimated = await loop.run_in_executor(
                None, w3.eth.estimate_gas, tx
            )
            tx["gas"] = int(estimated * 1.2)
        except Exception:
            tx["gas"] = 300000

        signed = w3.eth.account.sign_transaction(tx, account.private_key)
        tx_hash = await loop.run_in_executor(
            None, w3.eth.send_raw_transaction, signed.raw_transaction
        )

        tx_hex = tx_hash.hex()
        log_info(
            f"Contract call tx sent: {EXPLORER_URL}{tx_hex}",
            account.index,
            account.address,
        )

        receipt = await loop.run_in_executor(
            None, lambda: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        )

        if receipt.status == 1:
            log_success(
                f"Contract call confirmed | Gas: {receipt['gasUsed']}",
                account.index,
                account.address,
            )
            return tx_hex
        else:
            log_error(
                f"Contract call reverted: {EXPLORER_URL}{tx_hex}",
                account.index,
                account.address,
            )
            return None

    except Exception as e:
        log_error(
            f"Contract call failed: {e}",
            account.index,
            account.address,
        )
        return None
