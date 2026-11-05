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

# Select python binary (prefer local venv if available)
PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
    PYTHON_BIN="$(which python3 || echo "/usr/bin/python3")"
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting Job Radar sync ==="

MIN_SCORE="${JOB_RADAR_NOTIFY_MIN_SCORE:-70}"
"${PYTHON_BIN}" "${SCRIPT_DIR}/radar.py" sync --min-score="${MIN_SCORE}" --notify

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Job Radar sync finished ==="
