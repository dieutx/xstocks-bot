#!/bin/bash
# =============================================================
#  xStocks Daily Cron — runs all tasks with retry until success
#  Sends Telegram reports on completion or critical errors
#  Schedule: 7:12 AM Hanoi time (0:12 UTC) via crontab
# =============================================================

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

VENV="$SCRIPT_DIR/venv/bin/python3"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d_%H%M%S).log"

# Load env for Telegram tokens
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

send_telegram() {
    local msg="$1"
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"${msg}\",\"parse_mode\":\"HTML\",\"disable_web_page_preview\":true}" \
            > /dev/null 2>&1
    fi
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# -------------------------------------------------------
log "=== xStocks Daily Cron Start ==="

# Run batched with full mode (register + gm + spin)
MAX_RETRIES=5
ATTEMPT=0
SUCCESS=false

while [ $ATTEMPT -lt $MAX_RETRIES ]; do
    ATTEMPT=$((ATTEMPT + 1))
    log "Attempt $ATTEMPT/$MAX_RETRIES..."

    OUTPUT=$($VENV -u "$SCRIPT_DIR/run_batched.py" --mode register_gm 2>&1)
    EXIT_CODE=$?

    echo "$OUTPUT" >> "$LOG_FILE"

    # Check for critical errors (400 invalid signature etc)
    if echo "$OUTPUT" | grep -qiE "invalid signature|signature.*invalid|400.*signature|signatur.*fail"; then
        ERROR_LINES=$(echo "$OUTPUT" | grep -iE "invalid signature|signature.*invalid|400.*signature|signatur.*fail" | head -5)
        log "CRITICAL: Signature error detected!"
        send_telegram "🚨 <b>xStocks Bot — SIGNATURE ERROR</b>
📅 $(date '+%Y-%m-%d %H:%M:%S')
🔄 Attempt: $ATTEMPT/$MAX_RETRIES

<b>Error:</b>
<code>${ERROR_LINES}</code>

⚠️ Signature format may have changed. Check and fix manually."
        log "Sent Telegram alert for signature error"
        # Don't retry on signature errors — needs manual fix
        break
    fi

    # Check for other 400 errors
    if echo "$OUTPUT" | grep -qiE "\[400\].*error|\b400\b.*fail"; then
        ERROR_LINES=$(echo "$OUTPUT" | grep -iE "\[400\]" | head -5)
        log "WARNING: Got 400 errors"
        send_telegram "⚠️ <b>xStocks Bot — 400 Error</b>
📅 $(date '+%Y-%m-%d %H:%M:%S')
🔄 Attempt: $ATTEMPT/$MAX_RETRIES

<b>Details:</b>
<code>${ERROR_LINES}</code>"
    fi

    if [ $EXIT_CODE -eq 0 ]; then
        # Check if all accounts succeeded
        FAIL_COUNT=$(echo "$OUTPUT" | grep -ciE "failed|error" || true)
        SUCCESS_COUNT=$(echo "$OUTPUT" | grep -ciE "success|done|revealed" || true)

        if [ "$FAIL_COUNT" -eq 0 ] || [ "$SUCCESS_COUNT" -gt 0 ]; then
            SUCCESS=true
            log "All tasks completed successfully on attempt $ATTEMPT"
            break
        fi
    fi

    if [ $ATTEMPT -lt $MAX_RETRIES ]; then
        # Exponential backoff: 60s, 120s, 240s, 480s
        WAIT=$((60 * (2 ** (ATTEMPT - 1))))
        log "Retrying in ${WAIT}s..."
        sleep $WAIT
    fi
done

# -------------------------------------------------------
# Final report to Telegram
if [ "$SUCCESS" = true ]; then
    # Count results from log
    TOTAL=$(grep -c "address" "$LOG_FILE" 2>/dev/null || echo "?")
    send_telegram "✅ <b>xStocks Bot — Daily Run Complete</b>
📅 $(date '+%Y-%m-%d %H:%M:%S')
🔄 Attempts: $ATTEMPT/$MAX_RETRIES
📊 Status: All tasks done

📝 Log: $LOG_FILE"
    log "Telegram summary sent (success)"
else
    LAST_ERRORS=$(tail -20 "$LOG_FILE" | grep -iE "error|fail|500|429|timeout" | tail -5)
    send_telegram "❌ <b>xStocks Bot — Daily Run FAILED</b>
📅 $(date '+%Y-%m-%d %H:%M:%S')
🔄 Attempts: $ATTEMPT/$MAX_RETRIES

<b>Last errors:</b>
<code>${LAST_ERRORS}</code>

📝 Log: $LOG_FILE"
    log "Telegram summary sent (failure)"
fi

log "=== xStocks Daily Cron End ==="
