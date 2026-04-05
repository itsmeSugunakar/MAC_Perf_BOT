#!/usr/bin/env bash
# uninstall.sh — stop and remove all Performance Bot agents
set -euo pipefail

LA="$HOME/Library/LaunchAgents"

for plist in "com.user.performancebot.plist" "com.user.performancebot-gui.plist"; do
    DST="$LA/$plist"
    if [[ -f "$DST" ]]; then
        launchctl unload "$DST" 2>/dev/null || true
        rm "$DST"
        echo "✓ Removed $plist"
    fi
done

# Kill any running instance
pkill -f "performance_gui.py"  2>/dev/null || true
pkill -f "performance_bot.py"  2>/dev/null || true

echo "✓ Performance Bot fully uninstalled."
