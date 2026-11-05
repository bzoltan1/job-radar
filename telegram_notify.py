#!/usr/bin/env python3
"""Compatibility wrapper for radar.sinks.telegram_sink."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radar.sinks.telegram_sink import (
    format_jobs_html,
    get_telegram_creds,
    send_telegram_message,
)


def notify_new_jobs(jobs, token=None, chat_id=None):
    valid_jobs = [j for j in jobs if not any("loc:foreign_restriction" in t for t in getattr(j, "tags", []))]
    if not valid_jobs:
        return False
    msg = format_jobs_html(valid_jobs)
    return send_telegram_message(msg, token=token, chat_id=chat_id)
