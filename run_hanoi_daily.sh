#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

HANOI_DATE="$(TZ=Asia/Ho_Chi_Minh date +%F)"
RUN_LOG="$LOG_DIR/hanoi_daily_${HANOI_DATE}.log"

echo "[$(date '+%F %T')] GM đã bị disable vì xStocks không còn hỗ trợ GM. Script không làm gì." | tee -a "$RUN_LOG"
exit 0
