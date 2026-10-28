#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Export display and dbus if available for desktop notification
export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    USER_ID="$(id -u)"
    export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${USER_ID}/bus"
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting Job Radar sync ==="

/usr/bin/python3 "${SCRIPT_DIR}/radar.py" sync
/usr/bin/python3 "${SCRIPT_DIR}/obsidian_sync.py" --min-score=70 --notify

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Job Radar sync finished ==="
