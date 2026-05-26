#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="$PROJECT_DIR/venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
STATE_DIR="$PROJECT_DIR/state"
mkdir -p "$LOG_DIR" "$STATE_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[$(date '+%F %T')] Missing venv python: $PYTHON_BIN"
  exit 1
fi

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  . "$PROJECT_DIR/.env"
  set +a
fi

HANOI_DATE="$(TZ=Asia/Ho_Chi_Minh date +%F)"
HANOI_HHMM="$(TZ=Asia/Ho_Chi_Minh date +%H%M)"
RUN_LOG="$LOG_DIR/hanoi_reveal_${HANOI_DATE}.log"
COMPLETE_MARKER="$STATE_DIR/reveal_complete_${HANOI_DATE}"
FAIL_ALERT_MARKER="$STATE_DIR/reveal_fail_alert_${HANOI_DATE}"
FAIL_ALERT_COOLDOWN_SECONDS=3600

log() {
  echo "[$(date '+%F %T')] $1" | tee -a "$RUN_LOG"
}

send_telegram() {
  local msg="$1"
  if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    log "Telegram chưa cấu hình; bỏ qua notify"
    return 0
  fi

  curl -fsS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${msg}" \
    >/dev/null || log "Gửi Telegram thất bại"
}

should_send_fail_alert() {
  local now_ts last_ts
  now_ts="$(date +%s)"

  if [ ! -f "$FAIL_ALERT_MARKER" ]; then
    return 0
  fi

  last_ts="$(cat "$FAIL_ALERT_MARKER" 2>/dev/null || true)"
  if ! [[ "$last_ts" =~ ^[0-9]+$ ]]; then
    return 0
  fi

  if [ $((now_ts - last_ts)) -ge "$FAIL_ALERT_COOLDOWN_SECONDS" ]; then
    return 0
  fi

  return 1
}

mark_fail_alert_sent() {
  date +%s > "$FAIL_ALERT_MARKER"
}

if [ ! -f "$PROJECT_DIR/data/accounts.json" ]; then
  log "accounts.json chưa có, bỏ qua"
  exit 0
fi

if [ "$HANOI_HHMM" -lt "0800" ]; then
  log "Chưa tới 08:00 Hà Nội, bỏ qua"
  exit 0
fi

if [ -f "$COMPLETE_MARKER" ]; then
  log "Hôm nay đã reveal xong, không chạy nữa"
  exit 0
fi

if pgrep -f "python.*reveal_only.py" >/dev/null 2>&1; then
  log "reveal_only.py đang chạy, bỏ qua tick này"
  exit 0
fi

log "Bắt đầu reveal-only"
if "$PYTHON_BIN" "$PROJECT_DIR/reveal_only.py" 2>&1 | tee -a "$RUN_LOG"; then
  touch "$COMPLETE_MARKER"
  rm -f "$FAIL_ALERT_MARKER"
  log "Đã xác nhận reveal xong toàn bộ account cho ngày ${HANOI_DATE}"
  send_telegram "✅ xStocks reveal thành công\nNgày Hà Nội: ${HANOI_DATE}\nCron sẽ dừng retry cho hôm nay."
else
  log "Chưa reveal xong hết; cron sẽ retry sau 15 phút"
  if should_send_fail_alert; then
    send_telegram "⚠️ xStocks reveal chưa xong\nNgày Hà Nội: ${HANOI_DATE}\nCron sẽ retry sau 15 phút.\nLog: ${RUN_LOG}\nRate limit: tối đa 1 cảnh báo/giờ."
    mark_fail_alert_sent
  else
    log "Skip Telegram fail alert do đang trong cooldown"
  fi
fi
