# ARCHITECTURE.md — Code Structure

## Directory Layout

```
xstocks-bot/
├── CLAUDE.md               # System rules and hard constraints
├── README.md               # Human-readable overview
├── SKILL.md                # Agent operational behavior
├── ARCHITECTURE.md         # This file — code structure
├── DATA_MODEL.md           # Data schemas and persistence
├── TASKS.md                # Task tracking and execution plan
│
├── config.py               # All configuration constants
├── requirements.txt        # Python dependencies
│
├── generate_wallets.py     # Wallet generation + proxy assignment
├── run_batched.py          # Main execution engine (batched)
├── run_daily.sh            # Cron wrapper script
├── main.py                 # Legacy interactive menu (kept for manual use)
│
├── core/                   # Core business logic
│   ├── account.py          # BotAccount class (EVM wallets)
│   ├── solana_account.py   # SolanaAccount class (Solana wallets)
│   ├── http_client.py      # Anti-detection HTTP client (curl_cffi, Chrome TLS)
│   ├── api.py              # Legacy API interactions (kept for reference)
│   ├── blockchain.py       # On-chain interactions (web3.py)
│   └── tasks.py            # Task definitions and registry
│
├── utils/                  # Shared utilities
│   ├── logger.py           # Colored per-account logging
│   ├── proxy.py            # Proxy loader and validator
│   ├── helpers.py          # Retry, delay, key validation
│   └── telegram.py         # Telegram notification (tokens via env vars)
│
├── progress_report.py      # Telegram progress updates (cron every 20min)
│
└── data/                   # Data directory (GITIGNORED)
    ├── db.py               # Database operations (load, save, query)
    ├── accounts.json       # Persistent account DB (DO NOT COMMIT)
    ├── accounts.txt        # Legacy: private keys (read-only)
    └── proxies.txt         # Legacy: proxy list (read-only)
```

## Module Responsibilities

### Entry Points

| File | Purpose | When to Use |
|------|---------|-------------|
| `generate_wallets.py` | Generate wallets, import existing, assign proxies | First-time setup, adding proxies |
| `run_batched.py` | Batched execution with anti-detection | Registration + GM, or daily GM |
| `run_daily.sh` | Shell wrapper for cron | Automated daily runs |
| `main.py` | Interactive menu (legacy) | Manual testing, one-off tasks |

### Core Layer (`core/`)

| Module | Responsibility |
|--------|---------------|
| `account.py` | EVM wallet management. `BotAccount` class: key derivation, EIP-191 signing. Used for signing only (no session management in new flow). |
| `solana_account.py` | Solana wallet management. `SolanaAccount` class: Ed25519 signing (base64 output). Same interface as BotAccount. |
| `http_client.py` | Anti-detection HTTP client using `curl_cffi`. Chrome TLS fingerprint, per-account browser identity (UA, sec-ch-ua, platform, accept-language), ETag caching, weighted delays (log-normal distribution). locale matching your proxy region for Accept-Language headers. |
| `api.py` | Legacy API interactions (kept for reference). Not used by current `run_batched.py`. |
| `tasks.py` | Task definitions for the legacy `main.py` menu system. `TASK_REGISTRY` maps task keys to async functions. |

### Data Layer (`data/`)

| Module | Responsibility |
|--------|---------------|
| `db.py` | Database CRUD operations. Load/save JSON, generate wallets, assign proxies, create batches, query by status. |
| `accounts.json` | Persistent storage. Single source of truth for all account data, proxy mappings, and status. |

### Utils Layer (`utils/`)

| Module | Responsibility |
|--------|---------------|
| `logger.py` | Colored terminal output with per-account context (index + address). |
| `proxy.py` | Proxy file parsing, validation, pairing logic. |
| `helpers.py` | `retry_async()` with exponential backoff, `random_delay()`, key type detection, validation. |
| `telegram.py` | Send formatted summaries to Telegram group after each run. |

## Data Flow

```
generate_wallets.py
    │
    ├─→ data/db.py (generate wallets, import existing)
    ├─→ data/accounts.json (persist)
    └─→ proxy assignment (permanent pairing)

run_batched.py
    │
    ├─→ data/db.py (load DB, filter pending accounts)
    ├─→ make_batches() → randomized batches of 10-20
    │
    └─→ For each batch (concurrent):
        ├─→ core/http_client.py (create curl_cffi session with Chrome TLS)
        ├─→ Per-account fingerprint (generated once, stored in accounts.json)
        ├─→ Browser-like flow: xdrop-config → user check → dashboard + points-breakdown → spin → GM
        ├─→ core/account.py or core/solana_account.py (signing only)
        ├─→ data/db.py (mark_registered, mark_gm_done, save_db)
        ├─→ utils/telegram.py (send summary + failure alerts)
        └─→ Weighted delays (log-normal) between batches (5-15s)
```

## Key Design Decisions

1. **JSON over SQLite** — simpler for this scale (N accounts), human-readable, easy to debug
2. **Atomic saves** — write to `.tmp` then `os.replace()` to prevent corruption
3. **curl_cffi over aiohttp** — Chrome TLS fingerprint impersonation for anti-detection
4. **Per-account fingerprint** — UA, sec-ch-ua, platform, accept-language generated once and persisted in `accounts.json`
5. **Proxy pairing in DB** — stored as a field on each account record, never computed at runtime
6. **Weighted delays** — log-normal distribution clusters toward shorter waits with occasional longer pauses
7. **ETag caching** — per-URL ETag storage reduces redundant API responses
8. **Batched over parallel** — reduces API load, mimics human behavior, easier to debug
