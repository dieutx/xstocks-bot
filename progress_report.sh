#!/bin/bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR"
source venv/bin/activate
if [ -f .env ]; then
  set -a && . ./.env && set +a
fi
python progress_report.py
