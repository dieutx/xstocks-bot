#!/bin/bash
# Smart runner: handles 500 errors by reducing batch size, then stops and pings Telegram
cd /root/claude-xstocks
source venv/bin/activate
set -a && . .env && set +a

BATCH_SIZES=("40 60" "10 20" "1 2")
LOG=run_gm.log

send_telegram() {
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="$1" > /dev/null 2>&1
}

check_success_rate() {
    # Check last 5 batch results, return success rate (0-100)
    local success=0 total=0
    while read -r line; do
        local s=$(echo "$line" | grep -oP '(\d+)/\d+ success' | grep -oP '^\d+')
        local t=$(echo "$line" | grep -oP '\d+/(\d+) success' | grep -oP '/\d+' | tr -d '/')
        if [ -n "$s" ] && [ -n "$t" ]; then
            success=$((success + s))
            total=$((total + t))
        fi
    done < <(grep "Batch.*done.*success" "$LOG" | tail -5)

    if [ "$total" -gt 0 ]; then
        echo $((success * 100 / total))
    else
        echo 0
    fi
}

for i in "${!BATCH_SIZES[@]}"; do
    read -r MIN MAX <<< "${BATCH_SIZES[$i]}"

    # Update batch size in run_batched.py
    sed -i "s/make_batches(pending, min_size=[0-9]*, max_size=[0-9]*)/make_batches(pending, min_size=${MIN}, max_size=${MAX})/" run_batched.py

    echo "[$(date)] Starting with batch size ${MIN}-${MAX}"

    # Run bot
    export CRON_RUN=1
    python run_batched.py gm >> "$LOG" 2>&1 &
    BOT_PID=$!

    # Wait for some batches to complete
    sleep 180

    # Check if bot is still running
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo "[$(date)] Bot finished quickly"
        break
    fi

    RATE=$(check_success_rate)
    echo "[$(date)] Success rate: ${RATE}%"

    if [ "$RATE" -ge 30 ]; then
        echo "[$(date)] Success rate OK (${RATE}%), letting bot continue"
        wait $BOT_PID
        echo "[$(date)] Bot finished"
        break
    fi

    # Low success rate — stop bot
    kill $BOT_PID 2>/dev/null
    wait $BOT_PID 2>/dev/null
    echo "[$(date)] Stopped bot (${RATE}% success with batch ${MIN}-${MAX})"

    if [ "$i" -lt $((${#BATCH_SIZES[@]} - 1)) ]; then
        echo "[$(date)] Retrying with smaller batch size..."
        sleep 30
    else
        # All batch sizes failed — ping Telegram and stop
        echo "[$(date)] All batch sizes failed, alerting Telegram"
        send_telegram "🚨 <b>[xStocks Bot] Daily GM failed!</b>

API returning 500s at all batch sizes (40-60, 10-20, 1-2).
Success rate: ${RATE}%

Bot stopped. Manual retry needed."

        # Restore default batch size
        sed -i "s/make_batches(pending, min_size=[0-9]*, max_size=[0-9]*)/make_batches(pending, min_size=40, max_size=60)/" run_batched.py
        exit 1
    fi
done

# Restore default batch size
sed -i "s/make_batches(pending, min_size=[0-9]*, max_size=[0-9]*)/make_batches(pending, min_size=40, max_size=60)/" run_batched.py
echo "[$(date)] Done, batch size restored to 40-60"
