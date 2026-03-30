#!/bin/bash
set -e
PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR"
source venv/bin/activate
if [ -f .env ]; then
  set -a && . ./.env && set +a
fi

TODAY=$(date +%F)
TOTAL=$(python - <<'PY'
import json
from pathlib import Path
p = Path('data/accounts.json')
if not p.exists():
    print(0)
else:
    data = json.loads(p.read_text())
    print(len(data))
PY
)
GM_DONE=$(python - <<'PY'
import json
from pathlib import Path
from datetime import datetime
p = Path('data/accounts.json')
today = datetime.now().strftime('%Y-%m-%d')
if not p.exists():
    print(0)
else:
    data = json.loads(p.read_text())
    print(sum(1 for a in data if a.get('gm_last_date') == today))
PY
)

if [ "$TOTAL" -eq 0 ]; then
  echo "[$(date +%T)] No accounts configured; skipping retry cycle"
  exit 0
fi

if [ "$GM_DONE" -lt "$TOTAL" ]; then
  if pgrep -f "python.*run_batched.py" >/dev/null 2>&1; then
    echo "[$(date +%T)] run_batched.py already running; sending progress only"
  else
    echo "[$(date +%T)] Incomplete daily run ($GM_DONE/$TOTAL). Retrying GM..."
    export CRON_RUN=1
    python run_batched.py gm >> "$PROJECT_DIR/run_daily.log" 2>&1 || true
  fi
else
  echo "[$(date +%T)] Daily GM already complete ($GM_DONE/$TOTAL); no retry needed"
fi

python progress_report.py >> "$PROJECT_DIR/progress.log" 2>&1 || true
