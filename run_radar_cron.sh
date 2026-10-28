#!/usr/bin/env bash
# Compatibility wrapper for systemd user service job-radar.service
exec "$(dirname "$0")/run_sync.sh" "$@"
