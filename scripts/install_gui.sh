#!/usr/bin/env bash
# install_gui.sh — install Performance Bot GUI and set it to auto-start at login
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_NAME="com.user.performancebot-gui"
if [[ -f "$REPO_ROOT/${PLIST_NAME}.plist" ]]; then
    PLIST_SRC="$REPO_ROOT/${PLIST_NAME}.plist"
elif [[ -f "$REPO_ROOT/config/${PLIST_NAME}.plist" ]]; then
    PLIST_SRC="$REPO_ROOT/config/${PLIST_NAME}.plist"
else
    echo "Error: Could not find ${PLIST_NAME}.plist in '$REPO_ROOT' or '$REPO_ROOT/config'." >&2
    exit 1
fi
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs/performance-bot"

echo "╔══════════════════════════════════════╗"
echo "║   Performance Bot GUI — Installer    ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Dependencies ───────────────────────────────────────────────────────────
echo "→ Installing Python dependencies …"
pip3 install psutil -q
echo "  psutil ✓"

# ── 2. Detect python3 and patch the plist ─────────────────────────────────────
PY_PATH="$(which python3)"
echo "→ Python found: $PY_PATH"
sed -i '' "s|/usr/bin/python3|$PY_PATH|g" "$PLIST_SRC"

# ── 3. Create log directory ───────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ── 4. Stop old CLI background bot if running ─────────────────────────────────
OLD="$LAUNCH_AGENTS/com.user.performancebot.plist"
if [[ -f "$OLD" ]]; then
    launchctl unload "$OLD" 2>/dev/null || true
    echo "→ Stopped old CLI bot (GUI includes the engine now)."
fi

# ── 5. Install the GUI LaunchAgent ────────────────────────────────────────────
mkdir -p "$LAUNCH_AGENTS"
cp "$PLIST_SRC" "$PLIST_DST"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"
echo "→ LaunchAgent loaded — GUI will auto-start at every login."

# ── 6. Launch immediately ─────────────────────────────────────────────────────
echo "→ Opening Performance Bot GUI …"
open -a Terminal "$SCRIPT_DIR/performance_gui.py" 2>/dev/null || \
    nohup "$PY_PATH" "$SCRIPT_DIR/performance_gui.py" &
sleep 1   # give python a moment to start

echo ""
echo "✓ All done!"
echo ""
echo "  App script : $SCRIPT_DIR/performance_gui.py"
echo "  Auto-start : $PLIST_DST"
echo "  Logs       : $LOG_DIR/"
echo ""
echo "  Manual controls:"
echo "    Open     → python3 $SCRIPT_DIR/performance_gui.py"
echo "    Stop bot → launchctl unload $PLIST_DST"
echo "    Start bot→ launchctl load -w $PLIST_DST"
echo "    Remove   → bash $SCRIPT_DIR/uninstall.sh"
