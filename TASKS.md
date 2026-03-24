# TASKS.md — Execution Plan

## Phase 1: Infrastructure Setup ✅

- [x] Clone repository
- [x] Set up Python venv and install dependencies
- [x] Fix Solana signature encoding (base58 → base64)
- [x] Fix error handling (verify state before retrying)
- [x] Add Telegram notifications
- [x] Create persistent database layer (`data/db.py`)
- [x] Create batched execution engine (`run_batched.py`)
- [x] Create wallet generation script (`generate_wallets.py`)
- [x] Remove old cron jobs
- [x] Create project documentation (CLAUDE.md, SKILL.md, etc.)

## Phase 2: Wallet Generation ✅

- [x] Import 100 existing accounts with proxy pairings
- [x] Generate EVM + Solana wallets
- [x] Save all to `data/accounts.json`
- [x] Assign proxies to all accounts

## Phase 3: Registration ✅

- [x] Register all accounts with your referral code
- [x] Verify registration success via Telegram summary
- [x] Re-run for failed accounts
- [x] Confirm all N accounts registered (2 remaining edge cases)

## Phase 4: Daily GM Automation ✅

- [x] Run first GM for all accounts
- [x] Set up cron job: `0 8 * * * /root/claude-xstocks/run_daily.sh`
- [x] Set up progress reports every 20 minutes
- [x] Confirm Telegram notifications received

## Phase 5: Anti-Detection Upgrade ✅

- [x] Install `curl_cffi` for Chrome TLS fingerprint
- [x] Create `core/http_client.py` with per-account browser fingerprint
- [x] Set locale matching your proxy region for Accept-Language headers
- [x] Rewrite `run_batched.py` with browser-like request flow
- [x] Add daily spin multiplier reveal before GM
- [x] Add ETag caching
- [x] Add weighted delays (log-normal distribution)
- [x] Add spin retry on 429/500
- [x] Add GM retry with dashboard verification (3 attempts)
- [x] Add per-batch Telegram failure alerts [Bot Name]
- [x] Move Telegram tokens to env vars
- [x] Reduce batch sizes to 10-20 for API stability
- [x] Disable proxy IP resolution to save bandwidth
- [x] Update `run_daily.sh` with env loading and CRON_RUN jitter
- [x] Test and verify with live accounts
- [x] Push to GitHub (excluding sensitive data)

## Phase 6: Monitoring & Maintenance (Ongoing)

- [x] Verify daily runs via cron.log
- [ ] Check for persistent failures (accounts that fail repeatedly)
- [ ] Back up `accounts.json` periodically
- [ ] Monitor proxy health

---

## Current Status

**Phase 5 complete — Anti-detection upgrade deployed and running**

### Database State
```
Total accounts:    N
EVM wallets:       N
Solana wallets:    N
Registered:        N
With proxy:        N
Referral code:     YOUR_CODE
```

### Cron Schedule
```
0 8 * * *    Daily GM run (08:00 UTC)
*/20 * * * * Progress report to Telegram
```
