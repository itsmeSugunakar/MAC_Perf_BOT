#!/usr/bin/env bash
# install.sh — set up and start the Performance Bot LaunchAgent
set -euo pipefail

PLIST_NAME="com.user.performancebot"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/${PLIST_NAME}.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS/${PLIST_NAME}.plist"

# ── 1. Install psutil ────────────────────────────────────────────────────────
echo "→ Installing psutil …"
pip3 install psutil -q

# ── 2. Detect correct python3 path and patch the plist ──────────────────────
PY_PATH="$(which python3)"
echo "→ Python found at: $PY_PATH"
sed -i '' "s|/opt/homebrew/bin/python3|$PY_PATH|g" "$PLIST_SRC"

# ── 3. Copy plist to LaunchAgents ────────────────────────────────────────────
mkdir -p "$LAUNCH_AGENTS"
cp "$PLIST_SRC" "$PLIST_DST"
echo "→ Plist installed to $PLIST_DST"

# ── 4. Load (or reload) the agent ────────────────────────────────────────────
# Unload silently if already loaded
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"
echo "→ LaunchAgent loaded."

echo ""
echo "✓ Performance Bot is running!"
echo "  Logs : ~/Library/Logs/performance-bot/"
echo "  Stop : launchctl unload $PLIST_DST"
echo "  Start: launchctl load -w $PLIST_DST"
