#!/bin/bash
# One Paper Pot cycle on this Mac: pull, run all four pots, commit and push the results.
# launchd runs this every hour at :03 (see install.sh). Output goes to logs/run.log.
set -u
cd "$(dirname "$0")/../.." || exit 1
mkdir -p logs
exec >> logs/run.log 2>&1
echo "=== $(date -u '+%Y-%m-%d %H:%M:%S') UTC"

[ -f .env ] && { set -a; . ./.env; set +a; }
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git pull -q --rebase origin "$BRANCH" || echo "pull failed (offline?), running on local state"

.venv/bin/python -m predbot run || { echo "run failed"; exit 1; }

for f in paper_state.json value_state.json stocks_state.json crypto_state.json \
         trade_journal.csv value_journal.csv stocks_journal.csv crypto_journal.csv \
         postmortems.jsonl lessons.json llm_usage.jsonl dashboard.html; do
  [ -f "$f" ] && git add "$f"
done
git commit -q -m "Paper run $(date -u +%H:%MZ) (Mac)" || echo "nothing to commit"
git push -q origin "$BRANCH" || echo "push failed (results are still saved locally)"
