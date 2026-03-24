"""
Colored logging with per-account labels.
Each account gets a unique color from a rotating palette.
"""

import sys
from datetime import datetime, timezone

from colorama import Fore, Style, init

from config import ACCOUNT_COLORS, LOG_DATE_FORMAT

init(autoreset=True)

# Map color names to colorama codes
COLOR_MAP: dict[str, str] = {
    "cyan": Fore.CYAN,
    "green": Fore.GREEN,
    "yellow": Fore.YELLOW,
    "magenta": Fore.MAGENTA,
    "blue": Fore.BLUE,
    "red": Fore.RED,
    "white": Fore.WHITE,
    "bright_cyan": Fore.LIGHTCYAN_EX,
    "bright_green": Fore.LIGHTGREEN_EX,
    "bright_yellow": Fore.LIGHTYELLOW_EX,
    "bright_magenta": Fore.LIGHTMAGENTA_EX,
    "bright_blue": Fore.LIGHTBLUE_EX,
}

# Level styling
LEVEL_STYLES: dict[str, tuple[str, str]] = {
    "INFO": (Fore.CYAN, "INFO"),
    "SUCCESS": (Fore.GREEN, " OK "),
    "WARNING": (Fore.YELLOW, "WARN"),
    "ERROR": (Fore.RED, "FAIL"),
}


def get_account_color(index: int) -> str:
    """Get a colorama color code for the given account index (0-based)."""
    color_name = ACCOUNT_COLORS[index % len(ACCOUNT_COLORS)]
    return COLOR_MAP.get(color_name, Fore.WHITE)


def _short_address(address: str) -> str:
    """Shorten an Ethereum address: 0xAbC...xYz."""
    if len(address) >= 10:
        return f"{address[:6]}...{address[-4:]}"
    return address


def log(
    level: str,
    message: str,
    account_index: int | None = None,
    address: str | None = None,
) -> None:
    """
    Print a formatted log line.

    Args:
        level: One of INFO, SUCCESS, WARNING, ERROR.
        account_index: 0-based account index (None for system messages).
        address: Wallet address for the account label.
        message: The log message.
    """
    timestamp = datetime.now(timezone.utc).strftime(LOG_DATE_FORMAT)
    level_color, level_tag = LEVEL_STYLES.get(level, (Fore.WHITE, "????"))

    if account_index is not None and address:
        acct_color = get_account_color(account_index)
        short = _short_address(address)
        prefix = f"{acct_color}[Account {account_index + 1} | {short}]{Style.RESET_ALL}"
    else:
        prefix = f"{Fore.WHITE}[System]{Style.RESET_ALL}"

    line = (
        f"{Fore.WHITE}{timestamp}{Style.RESET_ALL} "
        f"{level_color}[{level_tag}]{Style.RESET_ALL} "
        f"{prefix} {message}"
    )
    print(line, flush=True)


def log_info(msg: str, account_index: int | None = None, address: str | None = None) -> None:
    log("INFO", msg, account_index, address)


def log_success(msg: str, account_index: int | None = None, address: str | None = None) -> None:
    log("SUCCESS", msg, account_index, address)


def log_warning(msg: str, account_index: int | None = None, address: str | None = None) -> None:
    log("WARNING", msg, account_index, address)


def log_error(msg: str, account_index: int | None = None, address: str | None = None) -> None:
    log("ERROR", msg, account_index, address)


def print_banner() -> None:
    """Print the xStocks DeFi Bot banner."""
    banner = r"""
 ██╗  ██╗███████╗████████╗ ██████╗  ██████╗██╗  ██╗███████╗
 ╚██╗██╔╝██╔════╝╚══██╔══╝██╔═══██╗██╔════╝██║ ██╔╝██╔════╝
  ╚███╔╝ ███████╗   ██║   ██║   ██║██║     █████╔╝ ███████╗
  ██╔██╗ ╚════██║   ██║   ██║   ██║██║     ██╔═██╗ ╚════██║
 ██╔╝ ██╗███████║   ██║   ╚██████╔╝╚██████╗██║  ╚██╗███████║
 ╚═╝  ╚═╝╚══════╝   ╚═╝    ╚═════╝  ╚═════╝╚═╝   ╚═╝╚══════╝
    """
    print(f"{Fore.GREEN}{banner}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'═' * 60}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}  xStocks DeFi Bot — Multi-Account Parallel Runner{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'═' * 60}{Style.RESET_ALL}")
    print()


def print_summary(results: list[dict]) -> None:
    """
    Print a summary table of results per account.

    Args:
        results: List of dicts with keys: index, address, status, details.
    """
    print()
    print(f"{Fore.GREEN}{'═' * 70}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'  SUMMARY':^70}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'═' * 70}{Style.RESET_ALL}")
    print(
        f"  {Fore.WHITE}{'#':<4} {'Address':<20} {'Status':<12} {'Details'}{Style.RESET_ALL}"
    )
    print(f"  {'-' * 62}")

    for r in results:
        idx = r["index"] + 1
        addr = _short_address(r["address"])
        status = r["status"]
        details = r.get("details", "")

        if status == "SUCCESS":
            status_colored = f"{Fore.GREEN}{status}{Style.RESET_ALL}"
        elif status == "FAILED":
            status_colored = f"{Fore.RED}{status}{Style.RESET_ALL}"
        else:
            status_colored = f"{Fore.YELLOW}{status}{Style.RESET_ALL}"

        print(f"  {idx:<4} {addr:<20} {status_colored:<21} {details}")

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    total = len(results)
    print(f"  {'-' * 62}")
    print(
        f"  {Fore.GREEN}Results: {success_count}/{total} successful{Style.RESET_ALL}"
    )
    print(f"{Fore.GREEN}{'═' * 70}{Style.RESET_ALL}")
    print()
