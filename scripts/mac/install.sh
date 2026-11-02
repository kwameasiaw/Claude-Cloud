#!/bin/bash
# Set up Paper Pot to run hourly on this Mac. Safe to run again.
set -eu
cd "$(dirname "$0")/../.."
DIR=$(pwd)
LABEL=com.paperpot.hourly
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Python 3.10+ (the code uses 3.10 syntax; macOS's built-in python3 is 3.9)
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    PY=$(command -v "$c"); break
  fi
done
[ -n "$PY" ] || { echo "Need Python 3.10 or newer. Install it with:  brew install python"; exit 1; }
echo "Using $PY"

# xgboost needs OpenMP on macOS
if command -v brew >/dev/null && ! brew list libomp >/dev/null 2>&1; then
  echo "Installing libomp (needed by xgboost)..."; brew install libomp
fi

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -c "import xgboost, anthropic, pydantic" && echo "Python packages OK"

if [ ! -f .env ]; then
  cat > .env <<'ENV'
# Alpaca paper-trading data keys (alpaca.markets > Paper account > API keys).
# Without them the stocks and crypto pots skip each run; the Polymarket pots still work.
APCA_API_KEY_ID=
APCA_API_SECRET_KEY=
# Optional: ANTHROPIC_API_KEY= for Claude news scoring and postmortems (costs API credit).
ENV
  echo "Created .env - add your Alpaca keys to it."
fi
grep -qxF '.env' .gitignore 2>/dev/null || printf '.env\n.venv/\nlogs/\n' >> .gitignore

chmod +x scripts/mac/hourly.sh
mkdir -p "$HOME/Library/LaunchAgents" logs
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/scripts/mac/hourly.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Minute</key><integer>3</integer></dict>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo
echo "Installed. Paper Pot will run every hour at :03 while this Mac is awake."
echo "Run one now:     bash scripts/mac/hourly.sh && tail -30 logs/run.log"
echo "See dashboard:   open dashboard.html"
echo "Stop it:         launchctl bootout gui/\$(id -u)/$LABEL"
