# XStock Bot — Multi-Account Automation

Automated bot for xStocks DeFi daily tasks with multi-wallet support, batched execution, and anti-detection behavior.

## What It Does

- Manages multiple wallets (EVM + Solana)
- Registers accounts on xStocks via Backed API
- Performs daily "Say GM" + daily spin multiplier reveal to earn points
- Anti-detection: Chrome TLS fingerprint (curl_cffi), per-account browser identity, locale matching your proxy region
- Runs in randomized batches (10-20) with weighted delays (log-normal distribution)
- Sends results + progress reports to Telegram group

## Quick Start

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Generate Wallets (First Time)

```bash
python generate_wallets.py
```

This imports existing accounts from `data/accounts.txt` and generates new wallets. All data is stored in `data/accounts.json`.

### 3. Assign Proxies

```bash
python generate_wallets.py --proxies data/new_proxies.txt
```

Each account gets permanently paired with one proxy. This mapping never changes.

### 4. Register + Say GM

```bash
python run_batched.py
```

Runs all unregistered accounts through registration, then Say GM. Accounts are processed in randomized batches of 10-20 with weighted delays between batches.

### 5. Daily GM Only

```bash
python run_batched.py gm
```

Skips registration, only does Say GM for accounts that haven't done it today.

### 6. Set Up Daily Cron

```bash
crontab -e
# Add:
0 8 * * * /root/claude-xstocks/run_daily.sh >> /root/claude-xstocks/cron.log 2>&1
*/20 * * * * cd /root/claude-xstocks && set -a && . .env && set +a && python progress_report.py >> progress.log 2>&1
```

Daily GM runs at 08:00 UTC. Progress reports sent to Telegram every 20 minutes.

## Key Features

- **Persistent storage** — all account data, proxy mappings, fingerprints, and status saved to `data/accounts.json`
- **Idempotent** — safe to restart, won't re-register or duplicate GM
- **Chrome TLS fingerprint** — `curl_cffi` with `impersonate="chrome"` for realistic TLS
- **Per-account browser identity** — UA, sec-ch-ua, platform, accept-language generated once and persisted
- **locale matching your proxy region** — Accept-Language headers match regional proxy IPs
- **Browser-like request flow** — xdrop-config → user check → dashboard + points-breakdown → spin → GM
- **Weighted delays** — log-normal distribution (human-like timing)
- **ETag caching** — reduces redundant API responses
- **Smart retries** — checks dashboard before retrying on 500/timeout; spin retries on 429
- **Mixed batches** — each batch contains both EVM and Solana accounts
- **Telegram alerts** — run summaries, failure alerts per batch, progress reports every 20min

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for code structure.
See [DATA_MODEL.md](DATA_MODEL.md) for data schemas.
See [CLAUDE.md](CLAUDE.md) for system rules and constraints.

## Security

- Private keys are stored in `data/accounts.json` (gitignored)
- Proxy credentials are masked in log output
- Never commit `data/` directory contents
