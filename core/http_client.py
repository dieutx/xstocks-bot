"""
Anti-detection HTTP client using curl_cffi.
Per-account browser fingerprint, Chrome TLS, proper header ordering.
"""

import random
import math
from curl_cffi.requests import AsyncSession

# Chrome versions pool for realistic fingerprints
CHROME_VERSIONS = [
    {"version": "134", "brand": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"'},
    {"version": "136", "brand": '"Chromium";v="136", "Not-A.Brand";v="24", "Google Chrome";v="136"'},
    {"version": "133", "brand": '"Chromium";v="133", "Not(A:Brand";v="99", "Google Chrome";v="133"'},
]

PLATFORMS = ["Windows", "macOS", "Linux"]

ACCEPT_LANGUAGES = [
    "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "vi,en-US;q=0.9,en;q=0.8",
    "vi-VN,vi;q=0.9,en;q=0.8",
    "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6",
    "en-US,en;q=0.9,vi;q=0.8",
    "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "vi-VN,vi;q=0.9,en-GB;q=0.8,en;q=0.7",
    "en,vi-VN;q=0.9,vi;q=0.8",
]

UA_TEMPLATES = {
    "Windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36",
    "macOS": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36",
    "Linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36",
}


def generate_fingerprint() -> dict:
    """Generate a consistent browser fingerprint for an account."""
    chrome = random.choice(CHROME_VERSIONS)
    platform = random.choice(PLATFORMS)
    lang = random.choice(ACCEPT_LANGUAGES)

    return {
        "chrome_version": chrome["version"],
        "sec_ch_ua": chrome["brand"],
        "platform": platform,
        "accept_language": lang,
        "user_agent": UA_TEMPLATES[platform].format(version=chrome["version"]),
    }


def build_headers(fingerprint: dict, method: str = "GET") -> dict:
    """
    Build Chrome-accurate headers in correct order.
    GET requests do NOT include content-type.
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": fingerprint["accept_language"],
    }

    # Content-type only for POST/PUT, never GET
    if method in ("POST", "PUT"):
        headers["content-type"] = "application/json"

    headers.update({
        "origin": "https://defi.xstocks.fi",
        "priority": "u=1, i",
        "referer": "https://defi.xstocks.fi/",
        "sec-ch-ua": fingerprint["sec_ch_ua"],
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": f'"{fingerprint["platform"]}"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": fingerprint["user_agent"],
    })

    return headers


def weighted_delay(min_s: float, max_s: float) -> float:
    """
    Human-like delay using log-normal distribution.
    Clusters toward shorter waits with occasional longer pauses.
    """
    mu = math.log(min_s + (max_s - min_s) * 0.3)
    sigma = 0.5
    delay = random.lognormvariate(mu, sigma)
    return max(min_s, min(max_s, delay))


async def create_session(proxy: str | None, fingerprint: dict) -> AsyncSession:
    """
    Create a curl_cffi async session with Chrome TLS fingerprint.
    """
    session = AsyncSession(
        impersonate="chrome",
        proxy=proxy,
        timeout=60,
        verify=False,
    )
    return session


async def api_get(
    session: AsyncSession,
    url: str,
    fingerprint: dict,
    etags: dict | None = None,
) -> tuple[int, dict | str | None, str | None]:
    """
    Perform a GET request with Chrome-like headers.
    Returns: (status_code, response_data, new_etag)
    """
    headers = build_headers(fingerprint, "GET")

    if etags and url in etags:
        headers["if-none-match"] = etags[url]

    resp = await session.get(url, headers=headers)

    new_etag = resp.headers.get("etag")

    if resp.status_code == 304:
        return 304, None, new_etag

    try:
        data = resp.json()
    except Exception:
        data = resp.text

    return resp.status_code, data, new_etag


async def api_post(
    session: AsyncSession,
    url: str,
    payload: dict,
    fingerprint: dict,
) -> tuple[int, dict | str | None]:
    """
    Perform a POST request with Chrome-like headers.
    Returns: (status_code, response_data)
    """
    headers = build_headers(fingerprint, "POST")
    resp = await session.post(url, json=payload, headers=headers)

    try:
        data = resp.json()
    except Exception:
        data = resp.text

    return resp.status_code, data


async def api_put(
    session: AsyncSession,
    url: str,
    payload: dict,
    fingerprint: dict,
) -> tuple[int, dict | str | None]:
    """
    Perform a PUT request with Chrome-like headers.
    Returns: (status_code, response_data)
    """
    headers = build_headers(fingerprint, "PUT")
    resp = await session.put(url, json=payload, headers=headers)

    try:
        data = resp.json()
    except Exception:
        data = resp.text

    return resp.status_code, data
