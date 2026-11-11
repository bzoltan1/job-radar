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

# Ensure local bin is in PATH (needed for systemd user services to find uv)
export PATH="${HOME}/.local/bin:${PATH}"

# Select runner: uv run preferred, fallback to venv or system python
UV_BIN="$(command -v uv || echo "${HOME}/.local/bin/uv")"
if [[ -x "${UV_BIN}" ]]; then
    PYTHON_CMD=("${UV_BIN}" "run" "--no-dev" "python")
elif [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]] && "${SCRIPT_DIR}/.venv/bin/python" -c "import yaml" &>/dev/null; then
    PYTHON_CMD=("${SCRIPT_DIR}/.venv/bin/python")
else
    PYTHON_CMD=("$(command -v python3 || echo "/usr/bin/python3")")
fi

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Starting Job Radar sync ==="

MIN_SCORE="${JOB_RADAR_NOTIFY_MIN_SCORE:-70}"
"${PYTHON_CMD[@]}" "${SCRIPT_DIR}/radar.py" sync --min-score="${MIN_SCORE}" --notify "$@"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] Job Radar sync finished ==="
