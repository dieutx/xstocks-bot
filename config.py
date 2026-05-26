"""
Configuration for xStocks DeFi Bot.
All endpoints, chain IDs, contract addresses, and settings.
"""

# --- Network Configuration ---
RPC_URLS: list[str] = [
    "https://sepolia.base.org",
    "https://base-sepolia-rpc.publicnode.com",
]
CHAIN_ID: int = 84532  # Base Sepolia
EXPLORER_URL: str = "https://sepolia.basescan.org/tx/"

# --- xStocks DeFi API ---
API_BASE_URL: str = "https://defi.xstocks.fi/api"
PLATFORM_URL: str = "https://defi.xstocks.fi"

# --- Backed API (xDrop tasks) ---
BACKED_API_BASE_URL: str = "https://points-api.xstocks.fi/api/v1"

# SIWE (Sign-In with Ethereum) configuration
SIWE_DOMAIN: str = "defi.xstocks.fi"
SIWE_URI: str = "https://defi.xstocks.fi"
SIWE_VERSION: str = "1"
SIWE_STATEMENT: str = "Sign in to xStocks DeFi"

# API Endpoints
ENDPOINTS: dict[str, str] = {
    "nonce": f"{API_BASE_URL}/auth/nonce",
    "login": f"{API_BASE_URL}/auth/login",
    "checkin": f"{API_BASE_URL}/user/checkin",
    "user_info": f"{API_BASE_URL}/user/info",
    "points": f"{API_BASE_URL}/user/points",
    "say_gm": f"{API_BASE_URL}/user/say-gm",
    # Backed / xDrop endpoints
    "backed_register": f"{BACKED_API_BASE_URL}/xdrop-user",
    "backed_get_user": f"{BACKED_API_BASE_URL}/xdrop-user/{{wallet}}",
    "backed_say_gm": f"{BACKED_API_BASE_URL}/xdrop-user/say-gm",
    "backed_dashboard": f"{BACKED_API_BASE_URL}/xdrop-user/{{wallet}}/dashboard",
    "daily_spin_multiplier": f"{BACKED_API_BASE_URL}/xdrop-user/daily-spin-multiplier",
}

# --- Registration ---
REFERRAL_CODE: str = "YOUR_REFERRAL_CODE"
REGISTER_MESSAGE_PREFIX: str = "By signing this message, I confirm wallet ownership and register for xPoints"
SAY_GM_MESSAGE: str = "Say GM"

# --- Human-like Delays ---
REGISTER_DELAY_MIN: float = 5.0   # seconds between account registrations
REGISTER_DELAY_MAX: float = 15.0
GM_CLICK_DELAY_MIN: float = 3.0   # seconds between GM clicks
GM_CLICK_DELAY_MAX: float = 8.0

# --- Request Configuration ---
REQUEST_TIMEOUT: int = 30  # seconds
MAX_RETRIES: int = 3
RETRY_BASE_DELAY: float = 2.0  # seconds, exponential backoff base
RATE_LIMIT_DELAY: float = 60.0  # seconds to wait on 429
RESOLVE_PROXY_IP: bool = False  # skip proxy IP lookup to save bandwidth

# --- Parallel Execution ---
ACCOUNT_START_DELAY_MIN: float = 1.0   # min seconds between account starts
ACCOUNT_START_DELAY_MAX: float = 5.0   # max seconds between account starts
MAX_STAGGER_WINDOW: float = 60.0       # all accounts spread within this many seconds max
TASK_DELAY_MIN: float = 2.0            # min seconds between tasks
TASK_DELAY_MAX: float = 5.0            # max seconds between tasks

# --- File Paths ---
ACCOUNTS_FILE: str = "data/accounts.txt"
PROXIES_FILE: str = "data/proxies.txt"

# --- HTTP Headers ---
DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": PLATFORM_URL,
    "Referer": f"{PLATFORM_URL}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# --- Logging ---
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# --- Account Colors (rotating palette for terminal output) ---
ACCOUNT_COLORS: list[str] = [
    "cyan",
    "green",
    "yellow",
    "magenta",
    "blue",
    "red",
    "white",
    "bright_cyan",
    "bright_green",
    "bright_yellow",
    "bright_magenta",
    "bright_blue",
]
