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
HANOI_HOUR="$(TZ=Asia/Ho_Chi_Minh date +%H)"
HANOI_MINUTE="$(TZ=Asia/Ho_Chi_Minh date +%M)"
HANOI_HHMM="${HANOI_HOUR}${HANOI_MINUTE}"
RUN_LOG="$LOG_DIR/hanoi_daily_${HANOI_DATE}.log"
COMPLETE_MARKER="$STATE_DIR/daily_complete_${HANOI_DATE}"
INITIAL_MARKER="$STATE_DIR/initial_attempt_${HANOI_DATE}"

log() {
  echo "[$(date '+%F %T')] $1" | tee -a "$RUN_LOG"
}

if [ ! -f "$PROJECT_DIR/data/accounts.json" ]; then
  log "accounts.json chưa có, bỏ qua"
  exit 0
fi

if [ "$HANOI_HHMM" -lt "0800" ]; then
  log "Chưa tới 08:00 Hà Nội (${HANOI_HOUR}:${HANOI_MINUTE}), bỏ qua"
  exit 0
fi

if [ -f "$COMPLETE_MARKER" ]; then
  log "Hôm nay đã hoàn tất GM + reveal, không chạy nữa"
  exit 0
fi

if pgrep -f "python.*run_batched.py" >/dev/null 2>&1; then
  log "run_batched.py đang chạy, bỏ qua tick này"
  exit 0
fi

export CRON_RUN=1

if [ ! -f "$INITIAL_MARKER" ]; then
  MODE="register_gm"
  touch "$INITIAL_MARKER"
else
  MODE="gm"
fi

log "Bắt đầu job mode=${MODE} (giờ Hà Nội ${HANOI_HOUR}:${HANOI_MINUTE})"
if [ "$MODE" = "register_gm" ]; then
  "$PYTHON_BIN" -u "$PROJECT_DIR/run_batched.py" 2>&1 | tee -a "$RUN_LOG" || true
else
  "$PYTHON_BIN" -u "$PROJECT_DIR/run_batched.py" gm 2>&1 | tee -a "$RUN_LOG" || true
fi

log "Xác minh trạng thái daily sau khi chạy"
if "$PYTHON_BIN" "$PROJECT_DIR/verify_daily_status.py" 2>&1 | tee -a "$RUN_LOG"; then
  touch "$COMPLETE_MARKER"
  log "Đã xác nhận toàn bộ account GM xong và reveal xong cho ngày ${HANOI_DATE}"
else
  log "Chưa hoàn tất toàn bộ account; cron sẽ retry sau 15 phút"
fi
