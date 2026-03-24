# DATA_MODEL.md — Data Schemas and Persistence

## Storage

All data is stored in `data/accounts.json` as a JSON array of account objects.

## Account Schema

```json
{
  "private_key": "string",
  "address": "string",
  "wallet_type": "Evm" | "Svm",
  "proxy": "string | null",
  "registered": true | false,
  "gm_last_date": "YYYY-MM-DD" | null,
  "created_at": "ISO 8601 timestamp",
  "fingerprint": {
    "chrome_version": "134",
    "sec_ch_ua": "\"Chromium\";v=\"134\", ...",
    "platform": "Windows | macOS | Linux",
    "accept_language": "vi-VN,vi;q=0.9,...",
    "user_agent": "Mozilla/5.0 ..."
  },
  "etags": { "url-key": "etag-value" }
}
```

### Field Definitions

| Field | Type | Mutable | Description |
|-------|------|---------|-------------|
| `private_key` | string | **NEVER** | Hex string (EVM) or base58 string (Solana). The wallet's secret key. |
| `address` | string | **NEVER** | Derived wallet address. Checksummed hex (EVM) or base58 pubkey (Solana). |
| `wallet_type` | string | **NEVER** | `"Evm"` or `"Svm"`. Determines signing method and API payload format. |
| `proxy` | string or null | **ONCE** | Proxy URL (`http://user:pass@host:port`). Assigned once, NEVER changed after. Null if unassigned. |
| `registered` | boolean | Yes → true only | Starts `false`. Set to `true` after successful registration OR server confirms account exists. **NEVER set back to false.** |
| `gm_last_date` | string or null | Yes | Date string `"YYYY-MM-DD"` of last successful GM. Reset daily by checking if it matches today. |
| `created_at` | string | **NEVER** | ISO 8601 timestamp of when the record was created. |
| `fingerprint` | object or null | **ONCE** | Per-account browser fingerprint (chrome_version, sec_ch_ua, platform, accept_language, user_agent). Generated on first run, persisted permanently. Vietnamese locale. |
| `etags` | object or null | Yes | Per-URL ETag cache for HTTP caching. Updated each run. |

### Immutability Rules

```
NEVER CHANGE:  private_key, address, wallet_type, created_at
SET ONCE:      proxy (null → value, then never change)
SET ONCE:      fingerprint (null → generated, then never change)
MONOTONIC:     registered (false → true, never back)
DAILY RESET:   gm_last_date (compared to today's date)
PER-RUN:       etags (updated with latest ETags from API)
```

## Proxy Assignment

### Rules
1. Each proxy is assigned to exactly ONE account
2. Each account has at most ONE proxy
3. Once assigned, the mapping is permanent
4. Proxy assignment is done by `assign_proxies()` in `data/db.py`
5. Already-used proxies are tracked by checking all existing `proxy` fields

### Assignment Algorithm
```
1. Collect all proxy URLs already in use (from DB)
2. Filter input proxy list to remove already-used ones
3. For each account with proxy == null:
   - Pop first available proxy
   - Assign it
4. Save DB
```

## Batch Structure

Batches are created at runtime (not persisted) by `make_batches()`:

```
Input:  list of account dicts
Output: list of batches, each batch is a list of 10-20 account dicts

Algorithm:
1. Separate accounts into EVM and Solana lists
2. Shuffle each list independently
3. Interleave proportionally (random selection weighted by type ratio)
4. Split interleaved list into chunks of random size [10, 20]
```

This ensures each batch has a natural mix of both wallet types.

## Persistence Rules

### When to Save

| Event | Action |
|-------|--------|
| Account registered successfully | `mark_registered()` + `save_db()` |
| Server confirms account exists | `mark_registered()` + `save_db()` |
| GM click successful | `mark_gm_done()` + `save_db()` |
| "Click limit reached" response | `mark_gm_done()` + `save_db()` |
| Dashboard shows 0 clicks remaining | `mark_gm_done()` + `save_db()` |
| New wallets generated | `save_db()` |
| Proxies assigned | `save_db()` |

### Atomic Write

```python
def save_db(accounts):
    tmp = str(DB_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(accounts, f, indent=2)
    os.replace(tmp, str(DB_FILE))  # atomic on same filesystem
```

This prevents corruption if the process is killed mid-write.

### Recovery

If `accounts.json` is corrupted:
1. Check if `accounts.json.tmp` exists (incomplete write)
2. Fall back to regenerating from `accounts.txt` + `proxies.txt` (existing accounts only)
3. New wallets would need to be regenerated (keys are lost)

**Recommendation**: Back up `accounts.json` regularly.

## Example Record

### EVM Account
```json
{
  "private_key": "0xabc123...your_private_key_here",
  "address": "0x1234...abcd",
  "wallet_type": "Evm",
  "proxy": "http://user:pass@proxy-host:port",
  "registered": true,
  "gm_last_date": "2026-03-21",
  "created_at": "2026-03-20T23:34:34.123456"
}
```

### Solana Account
```json
{
  "private_key": "your_base58_private_key_here",
  "address": "your_solana_pubkey_here",
  "wallet_type": "Svm",
  "proxy": "http://user:pass@proxy-host:port",
  "registered": true,
  "gm_last_date": "2026-03-21",
  "created_at": "2026-03-20T23:34:34.789012"
}
```

## Statistics Query

```python
from data.db import load_db

db = load_db()
total = len(db)
evm = sum(1 for a in db if a["wallet_type"] == "Evm")
solana = total - evm
registered = sum(1 for a in db if a["registered"])
with_proxy = sum(1 for a in db if a["proxy"])
gm_today = sum(1 for a in db if a["gm_last_date"] == "2026-03-21")
```
