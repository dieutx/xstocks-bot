"""
All API interactions for xStocks DeFi platform.
Handles authentication (SIWE), checkin/Say GM, user info, and points.
"""

import base64
import time
import uuid
from datetime import datetime, timezone

import aiohttp

from config import (
    ENDPOINTS,
    SIWE_DOMAIN,
    SIWE_URI,
    SIWE_VERSION,
    SIWE_STATEMENT,
    CHAIN_ID,
    REFERRAL_CODE,
    REGISTER_MESSAGE,
    SAY_GM_MESSAGE,
    GM_CLICK_DELAY_MIN,
    GM_CLICK_DELAY_MAX,
)
from core.account import BotAccount
from utils.helpers import retry_async, RateLimitError
from utils.logger import log_info, log_success, log_error, log_warning


def _build_siwe_message(
    address: str,
    nonce: str,
    issued_at: str,
    chain_id: int = CHAIN_ID,
) -> str:
    """
    Build a SIWE (EIP-4361) compliant message string.

    Args:
        address: Ethereum wallet address (checksummed).
        nonce: Server-provided nonce.
        issued_at: ISO 8601 timestamp.
        chain_id: Chain ID for the SIWE message.

    Returns:
        Formatted SIWE message string.
    """
    message = (
        f"{SIWE_DOMAIN} wants you to sign in with your Ethereum account:\n"
        f"{address}\n"
        f"\n"
        f"{SIWE_STATEMENT}\n"
        f"\n"
        f"URI: {SIWE_URI}\n"
        f"Version: {SIWE_VERSION}\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at}"
    )
    return message


async def _check_response(
    response: aiohttp.ClientResponse,
    account: BotAccount,
    context: str,
) -> dict | None:
    """Check HTTP response status and parse JSON. Returns None on failure."""
    if response.status == 429:
        raise RateLimitError(f"Rate limited during {context}")

    if response.status >= 400:
        body = await response.text()
        log_error(
            f"{context} failed (HTTP {response.status}): {body[:200]}",
            account.index,
            account.address,
        )
        return None

    try:
        return await response.json()
    except Exception as e:
        text = await response.text()
        log_error(
            f"{context} invalid JSON response: {text[:200]}",
            account.index,
            account.address,
        )
        return None


async def resolve_proxy_ip(account: "BotAccount") -> str | None:
    """
    Resolve the external IP address of the proxy by calling a public API.
    Returns the IP string or None on failure.
    """
    if not account.session:
        return None

    try:
        async with account.session.get(
            "https://api.ipify.org?format=json", timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("ip")
    except Exception:
        pass
    return None


_NOT_FOUND = object()  # Sentinel: account definitively does not exist


async def get_xdrop_user(account: "BotAccount") -> dict | None | object:
    """
    Check if a wallet is already registered on xDrop.
    GET https://api.backed.fi/xdrop/api/v1/xdrop-user/{walletAddress}

    Returns:
        User data dict if registered, _NOT_FOUND if definitively not registered,
        None if the check failed (timeout/error — unknown state).
    """
    if not account.session:
        return None

    url = ENDPOINTS["backed_get_user"].format(wallet=account.address)

    async def _request() -> dict | object | None:
        async with account.session.get(url) as resp:
            if resp.status == 404:
                return _NOT_FOUND
            if resp.status >= 400:
                return None
            try:
                data = await resp.json()
                if data.get("success") and data.get("data"):
                    return data["data"]
                return data
            except Exception:
                return None

    try:
        return await retry_async(
            _request,
            account_index=account.index,
            address=account.address,
        )
    except Exception:
        return None


async def get_nonce(account: BotAccount) -> str | None:
    """
    Request a nonce from the API for SIWE authentication.

    Args:
        account: The BotAccount to authenticate.

    Returns:
        Nonce string or None on failure.
    """
    if not account.session:
        log_error("No session available", account.index, account.address)
        return None

    async def _request() -> str | None:
        params = {"address": account.address}
        async with account.session.get(
            ENDPOINTS["nonce"], params=params
        ) as resp:
            data = await _check_response(resp, account, "Get nonce")
            if data is None:
                return None
            # Try common response shapes
            nonce = data.get("nonce") or data.get("data", {}).get("nonce") or data.get("result")
            if nonce:
                return str(nonce)
            # If the endpoint returns plain text nonce
            if isinstance(data, str):
                return data
            log_error(
                f"Unexpected nonce response: {data}",
                account.index,
                account.address,
            )
            return None

    try:
        return await retry_async(
            _request,
            account_index=account.index,
            address=account.address,
        )
    except Exception as e:
        log_error(f"Failed to get nonce: {e}", account.index, account.address)
        return None


async def login(account: BotAccount) -> bool:
    """
    Authenticate using SIWE flow: get nonce -> sign message -> send to login endpoint.

    Args:
        account: The BotAccount to authenticate.

    Returns:
        True if login succeeded, False otherwise.
    """
    if not account.session:
        log_error("No session available", account.index, account.address)
        return False

    log_info("Requesting authentication nonce...", account.index, account.address)
    nonce = await get_nonce(account)
    if not nonce:
        return False

    log_info("Signing SIWE message...", account.index, account.address)
    issued_at = datetime.now(timezone.utc).isoformat()
    message = _build_siwe_message(
        address=account.address,
        nonce=nonce,
        issued_at=issued_at,
    )

    try:
        signature = account.sign_message(message)
    except Exception as e:
        log_error(f"Failed to sign message: {e}", account.index, account.address)
        return False

    log_info("Sending login request...", account.index, account.address)

    async def _login_request() -> bool:
        payload = {
            "message": message,
            "signature": f"0x{signature}" if not signature.startswith("0x") else signature,
            "address": account.address,
        }
        async with account.session.post(
            ENDPOINTS["login"], json=payload
        ) as resp:
            data = await _check_response(resp, account, "Login")
            if data is None:
                return False

            # Extract token from response (try common patterns)
            token = (
                data.get("token")
                or data.get("accessToken")
                or data.get("access_token")
                or data.get("data", {}).get("token")
                or data.get("data", {}).get("accessToken")
            )

            if token:
                account.auth_token = token
                account.session.headers.update(
                    {"Authorization": f"Bearer {token}"}
                )
                log_success("Login successful!", account.index, account.address)
                return True

            # Some APIs return success without explicit token (session-based)
            if data.get("success") or data.get("status") == "ok" or resp.status == 200:
                log_success(
                    "Login successful (session-based auth)!",
                    account.index,
                    account.address,
                )
                return True

            log_error(
                f"Login response missing token: {data}",
                account.index,
                account.address,
            )
            return False

    try:
        return await retry_async(
            _login_request,
            account_index=account.index,
            address=account.address,
        )
    except Exception as e:
        log_error(f"Login failed: {e}", account.index, account.address)
        return False


async def say_gm(account: BotAccount) -> bool:
    """
    Perform the daily "Say GM" checkin task.
    Tries multiple endpoint patterns since the exact API is not publicly documented.

    Args:
        account: Authenticated BotAccount.

    Returns:
        True if checkin succeeded, False otherwise.
    """
    if not account.session:
        log_error("No session available", account.index, account.address)
        return False

    log_info("Performing daily Say GM checkin...", account.index, account.address)

    # Try the say_gm endpoint first, then checkin as fallback
    endpoints_to_try = [
        ("say_gm", ENDPOINTS.get("say_gm")),
        ("checkin", ENDPOINTS.get("checkin")),
    ]

    for name, url in endpoints_to_try:
        if not url:
            continue

        async def _checkin_request(endpoint_url: str = url) -> bool:
            async with account.session.post(endpoint_url, json={}) as resp:
                data = await _check_response(resp, account, f"Say GM ({name})")
                if data is None:
                    return False

                # Check for success indicators
                success = (
                    data.get("success")
                    or data.get("status") in ("ok", "success", True)
                    or data.get("data", {}).get("success")
                    or data.get("code") == 0
                    or resp.status == 200
                )

                if success:
                    points = (
                        data.get("points")
                        or data.get("data", {}).get("points")
                        or data.get("reward")
                        or "N/A"
                    )
                    msg = data.get("message") or data.get("msg") or "GM!"
                    log_success(
                        f"Say GM success! Points: {points} | {msg}",
                        account.index,
                        account.address,
                    )
                    return True

                return False

        try:
            result = await retry_async(
                _checkin_request,
                account_index=account.index,
                address=account.address,
            )
            if result:
                return True
        except Exception as e:
            log_warning(
                f"Say GM via {name} failed: {e}",
                account.index,
                account.address,
            )
            continue

    log_error("All Say GM endpoints failed", account.index, account.address)
    return False


async def register_user(account: "BotAccount | SolanaAccount") -> bool:
    """
    Register a new user on the Backed xDrop platform.
    - EVM: signs with EIP-191 personal_sign, hex signature (0x prefixed)
    - Solana: signs with Ed25519, base58 signature

    Args:
        account: BotAccount (EVM) or SolanaAccount to register.

    Returns:
        True if registration succeeded (or already registered), False on error.
    """
    if not account.session:
        log_error("No session available", account.index, account.address)
        return False

    wallet_type = account.wallet_type  # "Evm" or "Solana"
    log_info(f"Signing registration message ({wallet_type})...", account.index, account.address)
    try:
        raw_sig = account.sign_message(REGISTER_MESSAGE)
        if wallet_type == "Evm":
            signature = raw_sig if raw_sig.startswith("0x") else f"0x{raw_sig}"
        else:
            signature = raw_sig  # Solana: base58 encoded Ed25519 signature
    except Exception as e:
        log_error(f"Failed to sign registration message: {e}", account.index, account.address)
        return False

    payload = {
        "walletAddress": account.address,
        "walletType": wallet_type,
        "signature": signature,
        "referredBy": REFERRAL_CODE,
    }

    async def _do_register() -> bool | None:
        """Attempt registration. Returns True=success, False=real failure, None=error/timeout."""
        async with account.session.post(
            ENDPOINTS["backed_register"], json=payload
        ) as resp:
            # 400/409 with "already exists" — treat as success
            if resp.status in (400, 409):
                text = await resp.text()
                if "already exists" in text.lower() or "already registered" in text.lower() or resp.status == 409:
                    log_info(
                        "Account already registered, continuing",
                        account.index,
                        account.address,
                    )
                    return True
                # Other 400 errors — real failure
                log_error(
                    f"Register user failed (HTTP {resp.status}): {text[:200]}",
                    account.index,
                    account.address,
                )
                return False

            # 500 server error — unknown state
            if resp.status == 500:
                body = await resp.text()
                log_warning(
                    f"Registration got 500: {body[:100]}",
                    account.index,
                    account.address,
                )
                return None

            data = await _check_response(resp, account, "Register user")
            if data is None:
                return None

            if (
                data.get("success")
                or data.get("data")
                or resp.status in (200, 201)
            ):
                user_id = (data.get("data") or {}).get("userId", "")
                log_success(
                    f"Registration successful! userId: {user_id}",
                    account.index,
                    account.address,
                )
                return True

            log_error(
                f"Registration unexpected response: {data}",
                account.index,
                account.address,
            )
            return False

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            result = await _do_register()
        except Exception as e:
            err_msg = str(e) or f"{type(e).__name__} (no message)"
            log_warning(
                f"Registration attempt {attempt}/{max_attempts} failed: {err_msg}",
                account.index,
                account.address,
            )
            result = None

        if result is True:
            return True
        if result is False:
            return False

        # result is None — error/timeout, check if registration actually went through
        log_info("Checking if registration went through...", account.index, account.address)
        user_data = await get_xdrop_user(account)
        if user_data and user_data is not _NOT_FOUND:
            log_info("Registration confirmed via account check", account.index, account.address)
            return True
        if user_data is _NOT_FOUND:
            log_info("Account still not registered, will retry...", account.index, account.address)
            continue
        # user_data is None — check also failed, try once more
        if attempt < max_attempts:
            log_warning("Could not verify registration status, retrying...", account.index, account.address)

    log_error("Registration failed after all attempts", account.index, account.address)
    return False


async def get_dashboard(account: BotAccount) -> dict | None:
    """
    Fetch the xDrop dashboard for the account.
    Returns the data dict (contains gmClicksRemaining, totalPoints, etc.) or None.

    Args:
        account: Authenticated BotAccount.

    Returns:
        Dashboard data dict or None.
    """
    if not account.session:
        return None

    url = ENDPOINTS["backed_dashboard"].format(wallet=account.address)

    async def _request() -> dict | None:
        async with account.session.get(url) as resp:
            data = await _check_response(resp, account, "Dashboard")
            if data:
                return data.get("data") or data
            return None

    try:
        return await retry_async(
            _request,
            account_index=account.index,
            address=account.address,
        )
    except Exception as e:
        log_warning(f"Failed to get dashboard: {e}", account.index, account.address)
        return None


async def backed_say_gm(account: BotAccount) -> int:
    """
    Call the Backed say-gm endpoint repeatedly until clicksRemaining reaches 0.
    Signs "Say GM" with EIP-191 personal_sign (hex signature, not base64).
    Handles 500 server errors gracefully with retry.

    Args:
        account: BotAccount (session must be open; no login required for Backed API).

    Returns:
        Number of successful GM clicks performed.
    """
    if not account.session:
        log_error("No session available", account.index, account.address)
        return 0

    log_info("Signing Say GM message...", account.index, account.address)
    try:
        raw_sig = account.sign_message(SAY_GM_MESSAGE)
        if account.wallet_type == "Evm":
            signature = raw_sig if raw_sig.startswith("0x") else f"0x{raw_sig}"
        else:
            signature = raw_sig  # Solana: base58
    except Exception as e:
        log_error(f"Failed to sign Say GM message: {e}", account.index, account.address)
        return 0

    payload = {
        "walletAddress": account.address,
        "signature": signature,
    }

    success_count = 0
    click_num = 0

    # Sentinels for flow control
    _STOP = object()   # GM done, no more clicks
    _ERROR = object()  # Request failed (timeout/500), need dashboard check

    while True:
        click_num += 1
        log_info(f"Say GM click #{click_num}...", account.index, account.address)

        async def _gm_click() -> dict | None:
            async with account.session.post(
                ENDPOINTS["backed_say_gm"], json=payload
            ) as resp:
                body = await resp.text()
                log_info(f"Response [{resp.status}]: {body[:200]}", account.index, account.address)

                # 500 server errors — don't blindly retry, return _ERROR
                # so we can check dashboard first
                if resp.status == 500:
                    return _ERROR  # type: ignore[return-value]

                # 400/409 = click limit reached or already done — stop
                if resp.status in (400, 409):
                    log_info(
                        "No more GM clicks available (already done)",
                        account.index,
                        account.address,
                    )
                    return _STOP  # type: ignore[return-value]

                if resp.status >= 400:
                    log_error(
                        f"Say GM failed (HTTP {resp.status}): {body[:150]}",
                        account.index,
                        account.address,
                    )
                    return None

                try:
                    import json as _json
                    return _json.loads(body)
                except Exception:
                    log_error(f"Invalid JSON response: {body[:100]}", account.index, account.address)
                    return None

        try:
            data = await _gm_click()
        except Exception as e:
            # Timeout or connection error — check dashboard before retrying
            err_msg = str(e) or f"{type(e).__name__} (no message)"
            log_warning(f"Say GM click #{click_num} failed: {err_msg}", account.index, account.address)
            data = _ERROR

        if data is _STOP:
            break

        if data is _ERROR or data is None:
            # Request failed — check dashboard to see if the click actually went through
            log_info("Checking dashboard to verify GM status...", account.index, account.address)
            dashboard = await get_dashboard(account)
            if dashboard:
                gm_remaining = int(dashboard.get("gmClicksRemaining", 0))
                log_info(f"Dashboard says GM clicks remaining: {gm_remaining}", account.index, account.address)
                if gm_remaining <= 0:
                    log_info("GM already completed (confirmed by dashboard)", account.index, account.address)
                    break
                else:
                    log_info(f"GM still needed ({gm_remaining} remaining), retrying...", account.index, account.address)
                    continue
            else:
                log_warning("Dashboard check also failed, stopping GM attempts", account.index, account.address)
                break

        # Parse success response
        inner = data.get("data") or data
        if not (data.get("success") or inner.get("walletAddress")):
            log_error(f"Unexpected Say GM response: {data}", account.index, account.address)
            break

        success_count += 1
        clicks_remaining = int(inner.get("clicksRemaining", 0))
        points_after = inner.get("gmPointsAfter") or inner.get("totalDailyPoints") or "?"
        points_added = inner.get("pointsAdded") or "?"
        log_success(
            f"Say GM click #{click_num} done! +{points_added} pts | Total: {points_after} | Remaining: {clicks_remaining}",
            account.index,
            account.address,
        )

        if clicks_remaining <= 0:
            log_info("All GM clicks used.", account.index, account.address)
            break

        # Human-like delay before next click
        delay = await random_delay(GM_CLICK_DELAY_MIN, GM_CLICK_DELAY_MAX)
        log_info(f"Waiting {delay:.1f}s before next click...", account.index, account.address)

    log_info(
        f"Say GM finished: {success_count} successful click(s)",
        account.index,
        account.address,
    )
    return success_count


async def get_user_info(account: BotAccount) -> dict | None:
    """
    Fetch user profile / info from the API.

    Args:
        account: Authenticated BotAccount.

    Returns:
        User info dict or None.
    """
    if not account.session:
        return None

    async def _request() -> dict | None:
        async with account.session.get(ENDPOINTS["user_info"]) as resp:
            data = await _check_response(resp, account, "User info")
            if data:
                info = data.get("data") or data
                log_info(
                    f"User info retrieved: {info}",
                    account.index,
                    account.address,
                )
                return info
            return None

    try:
        return await retry_async(
            _request,
            account_index=account.index,
            address=account.address,
        )
    except Exception as e:
        log_warning(f"Failed to get user info: {e}", account.index, account.address)
        return None


SPIN_MESSAGE_PREFIX = "Reveal daily spin multiplier"


async def daily_spin_multiplier(account: "BotAccount") -> bool:
    """
    Reveal the daily spin multiplier.
    PUT /xdrop-user/daily-spin-multiplier
    Signs the message "Reveal daily spin multiplier".

    Args:
        account: BotAccount or SolanaAccount (session must be open).

    Returns:
        True if revealed (or already revealed), False on error.
    """
    if not account.session:
        log_error("No session available", account.index, account.address)
        return False

    log_info("Revealing daily spin multiplier...", account.index, account.address)

    import time
    sign_ts = int(time.time())
    spin_msg = f"{SPIN_MESSAGE_PREFIX} | {sign_ts}"

    try:
        raw_sig = account.sign_message(spin_msg)
        if account.wallet_type == "Evm":
            signature = raw_sig if raw_sig.startswith("0x") else f"0x{raw_sig}"
        else:
            signature = raw_sig  # Solana: already base64 from sign_message
    except Exception as e:
        log_error(f"Failed to sign spin message: {e}", account.index, account.address)
        return False

    payload = {
        "walletAddress": account.address,
        "signature": signature,
        "signMethod": "message",
        "signTimestamp": sign_ts,
    }

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            async with account.session.put(
                ENDPOINTS["daily_spin_multiplier"], json=payload
            ) as resp:
                body = await resp.text()
                log_info(f"Spin response [{resp.status}]: {body[:200]}", account.index, account.address)

                if resp.status in (200, 201):
                    log_success("Daily spin multiplier revealed!", account.index, account.address)
                    return True

                if resp.status in (400, 409):
                    log_info("Spin multiplier already revealed or not available", account.index, account.address)
                    return True

                if resp.status == 500:
                    log_warning(f"Spin got 500, checking dashboard...", account.index, account.address)
                    # Fall through to dashboard check below

        except Exception as e:
            err_msg = str(e) or f"{type(e).__name__}"
            log_warning(f"Spin attempt {attempt}/{max_attempts} failed: {err_msg}", account.index, account.address)

        # Verify via dashboard before retrying
        dashboard = await get_dashboard(account)
        if dashboard:
            revealed = dashboard.get("dailySpinMultiplierRevealed")
            if revealed is True:
                log_info("Spin confirmed revealed via dashboard", account.index, account.address)
                return True
            if revealed is False and attempt < max_attempts:
                log_info("Spin still not revealed, retrying...", account.index, account.address)
                continue
        else:
            if attempt < max_attempts:
                log_warning("Dashboard check failed, retrying spin...", account.index, account.address)
                continue

    log_warning("Spin multiplier reveal failed after all attempts", account.index, account.address)
    return False


async def get_points(account: BotAccount) -> dict | None:
    """
    Fetch current points balance from the API.

    Args:
        account: Authenticated BotAccount.

    Returns:
        Points data dict or None.
    """
    if not account.session:
        return None

    async def _request() -> dict | None:
        async with account.session.get(ENDPOINTS["points"]) as resp:
            data = await _check_response(resp, account, "Points")
            if data:
                points_data = data.get("data") or data
                total = (
                    points_data.get("total")
                    or points_data.get("points")
                    or points_data.get("balance")
                    or "N/A"
                )
                log_info(
                    f"Current points: {total}",
                    account.index,
                    account.address,
                )
                return points_data
            return None

    try:
        return await retry_async(
            _request,
            account_index=account.index,
            address=account.address,
        )
    except Exception as e:
        log_warning(f"Failed to get points: {e}", account.index, account.address)
        return None
