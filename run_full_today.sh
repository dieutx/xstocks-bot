#!/bin/bash
# Run registration for new accounts, then GM for all (including old 100)
cd /root/claude-xstocks
source venv/bin/activate

echo "=== Phase 1: Register + GM for new accounts ==="
python run_batched.py

echo ""
echo "=== Phase 2: GM for any remaining accounts (old + failed) ==="
python run_batched.py gm
