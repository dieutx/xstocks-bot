# SKILL.md — Agent Operational Behavior

Rules for how the AI agent (Claude Code) should approach work on this project.

## Priority Order

```
1. Data safety     — never lose or corrupt existing data
2. Correctness     — verify state before acting
3. Reliability     — handle errors gracefully
4. Anti-detection  — randomize everything
5. Speed           — last priority
```

**Safety > Speed. Always.**

## Coding Style

### General
- Python 3.10+ with type hints
- Async/await for all I/O (curl_cffi AsyncSession for API, aiohttp legacy)
- Modular: one responsibility per file
- No magic numbers — use config.py constants
- Keep functions short (<50 lines)

### Naming
- `snake_case` for functions and variables
- `PascalCase` for classes
- `UPPER_CASE` for constants
- Prefix private helpers with `_`

### Error Handling
- Never swallow exceptions silently
- Log all errors with account context (index + address)
- Distinguish between "expected" outcomes (already registered, click limit) and real errors
- Use INFO for expected outcomes, WARNING for recoverable issues, ERROR for failures

### Imports
- Standard library first, then third-party, then local
- Explicit imports (no wildcard `*`)

## Persistence Rules

### Before ANY Destructive Operation
1. Load current state from `accounts.json`
2. Verify the account exists in DB
3. Perform the operation
4. Update DB immediately after success
5. Save DB to disk (atomic write via tmp + rename)

### What Gets Persisted
- `registered: true` — after successful registration or "already exists" response
- `gm_last_date: "YYYY-MM-DD"` — after successful GM or "click limit" response
- `proxy: "url"` — assigned once, NEVER changed

### What Does NOT Get Persisted
- Session tokens (ephemeral, per-run)
- Proxy IPs (not resolved — disabled to save bandwidth)
- Intermediate retry state

### What Gets Persisted (New)
- `fingerprint` — per-account browser identity (generated once on first run)
- `etags` — per-URL ETag cache (updated each run)

## How to Handle Existing Data

### DO
- Check if account exists in DB before adding
- Check if registered on server before attempting registration
- Check dashboard before attempting GM
- Preserve all fields when updating a record

### DO NOT
- Overwrite `accounts.json` without loading it first
- Remove accounts from DB
- Change the `private_key` or `proxy` fields of existing records
- Assume DB state matches server state (always verify)

## Anti-Detection Behavior

### HTTP Client
- Use `curl_cffi` with `impersonate="chrome"` — Chrome TLS fingerprint
- Per-account fingerprint: UA, sec-ch-ua, sec-ch-ua-platform, accept-language
- locale matching your proxy region for Accept-Language headers
- Full Chrome headers: sec-fetch-*, priority, proper accept
- No content-type on GET requests (browsers don't send it)
- ETag caching with If-None-Match

### Timing
- Use `weighted_delay(min, max)` — log-normal distribution, never uniform
- Inter-batch delays: 5-15 seconds (weighted)
- Post-registration pause: 1-3 seconds (weighted)
- Pre-dashboard pause: 0.5-1.5 seconds
- Post-spin pause: 0.5-2.0 seconds
- Startup jitter: 0-60 seconds (cron only, via CRON_RUN env var)

### Request Flow (Browser-Like)
1. GET /xdrop-config (preflight, like browser loading page)
2. GET /xdrop-user/{wallet} (check registration)
3. GET dashboard + points-breakdown (parallel, like browser)
4. PUT daily-spin-multiplier (if not revealed)
5. POST say-gm

### Ordering
- Shuffle account order every run
- BUT preserve account-proxy-fingerprint mapping
- Mix EVM and Solana in every batch

### Patterns to Avoid
- Running accounts in the same order twice
- Equal time gaps between operations
- Running all of one type before another
- Burst activity followed by silence
- Using aiohttp (detectable TLS fingerprint) — use curl_cffi instead

## API Interaction Rules

1. **Check before act** — always verify server state before mutating
2. **Verify after error** — on timeout/500, check if the action succeeded before retrying
3. **Respect rate limits** — if 429, wait 60 seconds
4. **Log everything** — response status + body for debugging
5. **Mask credentials** — never log full proxy URLs or private keys

## Telegram Notifications

- Send summary after EVERY run (success or failure)
- Include: success count, failure count, failed account details
- Keep messages concise — Telegram has 4096 char limit
- Use HTML parse mode for formatting

## When Modifying Code

1. Read the existing file first
2. Understand the current logic before changing
3. Make minimal changes — don't refactor unrelated code
4. Verify imports compile after changes
5. Test with a small subset before running full
6. Commit with descriptive messages
