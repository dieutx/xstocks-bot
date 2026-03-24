# CLAUDE.md — System Rules for XStock Bot

## Project Overview

Automation bot for xStocks DeFi platform. Manages multiple wallets (EVM + Solana). Registers accounts and performs daily "Say GM" + daily spin multiplier tasks via the Backed API. Uses curl_cffi for Chrome TLS fingerprint anti-detection with locale matching your proxy region.

## Hard Constraints — DO NOT VIOLATE

1. **DO NOT** change any existing account-proxy pairing. Once assigned, it is permanent.
2. **DO NOT** overwrite or regenerate existing wallets. Existing keys in `data/accounts.json` are sacred.
3. **DO NOT** re-register accounts that are already marked `registered: true`.
4. **DO NOT** re-attempt GM for accounts where `gm_last_date` matches today.
5. **DO NOT** hardcode secrets in committed files. Private keys and proxies live only in `data/` (gitignored).
6. **DO NOT** run all accounts simultaneously. Use batched execution (10-20 per batch).
7. **DO NOT** use uniform/predictable timing. All delays must use weighted_delay() (log-normal).
8. **DO NOT** hardcode Telegram tokens in code. Use environment variables via `.env`.

## Execution Flow

### Registration + GM (`run_batched.py`)
```
1. Load accounts.json
2. Filter: unregistered OR GM not done today
3. Optional startup jitter (0-60s if CRON_RUN=1)
4. Split into batches (10-20, mixed EVM/Solana)
5. For each batch (all accounts concurrent):
   Per account (browser-like flow via curl_cffi):
      a. Generate/load fingerprint (UA, sec-ch-ua, platform, accept-language)
      b. GET /xdrop-config (browser preflight)
      c. Check if registered (GET /xdrop-user/{wallet})
      d. If not found → register (POST /xdrop-user)
      e. GET dashboard + points-breakdown (parallel, with ETag caching)
      f. Reveal daily spin multiplier if needed (PUT, with 429/500 retry)
      g. Say GM (POST, with 3x retry + dashboard verification)
      h. Mark status in DB, save immediately
   Weighted delay between batches (5-15s, log-normal)
   Alert Telegram on batch failures
6. Send Telegram summary
```

### GM Only (`run_batched.py gm`)
```
1. Load accounts.json
2. Filter: gm_last_date != today
3. Same flow as above, skip registration step
```

## Anti-Detection Strategy

- **Chrome TLS fingerprint**: `curl_cffi` with `impersonate="chrome"`
- **Per-account browser identity**: UA, sec-ch-ua, sec-ch-ua-platform, accept-language — generated once, stored in `accounts.json`
- **locale matching your proxy region**: Accept-Language headers match regional proxy IPs
- **Full Chrome headers**: sec-ch-ua, sec-fetch-*, priority, proper accept; no content-type on GET
- **Browser request flow**: xdrop-config → user check → dashboard + points-breakdown parallel → spin → GM
- **Weighted delays**: log-normal distribution via `weighted_delay()` — clusters toward shorter waits
- **ETag caching**: per-URL ETag storage and If-None-Match headers
- **Batch sizes**: random 10-20 accounts
- **Inter-batch delay**: 5-15s (weighted, log-normal)
- **Account order**: shuffled every run (proxy mapping stays fixed)
- **Mixed batches**: each batch contains both EVM and Solana wallets

## API Endpoints

- Config: `GET https://api.backed.fi/xdrop/api/v1/xdrop-config`
- Register: `POST https://api.backed.fi/xdrop/api/v1/xdrop-user`
- Check user: `GET https://api.backed.fi/xdrop/api/v1/xdrop-user/{wallet}`
- Dashboard: `GET https://api.backed.fi/xdrop/api/v1/xdrop-user/{wallet}/dashboard`
- Points breakdown: `GET https://api.backed.fi/xdrop/api/v1/xdrop-user/{wallet}/points-breakdown`
- Daily spin: `PUT https://api.backed.fi/xdrop/api/v1/xdrop-user/daily-spin-multiplier`
- Say GM: `POST https://api.backed.fi/xdrop/api/v1/xdrop-user/say-gm`

## Signature Formats

- **EVM**: EIP-191 personal_sign → hex with `0x` prefix
- **Solana (Svm)**: Ed25519 sign raw bytes → **base64** encoded (NOT base58)

## Sign Messages

- Registration: `"By signing this message, I confirm wallet ownership and register for xPoints"`
- Say GM: `"Say GM"`
- Daily Spin: `"Daily Spin Multiplier"`

## Error Handling

- On timeout/500 during Say GM → check dashboard before retrying
- On timeout/500 during registration → check get_xdrop_user before retrying
- Never blindly retry — always verify state first
- 400 "already exists" → treat as success
- 400 "click limit reached" → treat as success (GM done)

## Referral Code

All new registrations use referral code: your referral code

## Telegram Notifications

Bot token and chat ID are loaded from environment variables (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) via `.env` file. Summary is sent after each run. Failure alerts are sent per-batch with `[Bot Name]` label. Progress reports run every 20 minutes via cron.

## File Structure

```
data/accounts.json    — persistent DB (DO NOT commit)
data/accounts.txt     — legacy format (read-only, for import)
data/proxies.txt      — legacy format (read-only, for import)
data/db.py            — database operations
run_batched.py        — main execution engine
generate_wallets.py   — wallet generation + proxy assignment
run_daily.sh          — cron wrapper script
```

## Commands

```bash
# Generate wallets (first time only)
python generate_wallets.py

# Assign proxies
python generate_wallets.py --proxies data/new_proxies.txt

# Run registration + GM
python run_batched.py

# Run GM only (daily)
python run_batched.py gm

# Cron: daily GM at 08:00 UTC
# 0 8 * * * /root/claude-xstocks/run_daily.sh >> /root/claude-xstocks/cron.log 2>&1
# Progress report every 20min
# */20 * * * * cd /root/claude-xstocks && ... python progress_report.py
```
