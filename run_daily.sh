#!/bin/bash
cd /root/claude-xstocks
source venv/bin/activate
set -a && . /root/claude-xstocks/.env && set +a
export CRON_RUN=1
python run_batched.py gm
