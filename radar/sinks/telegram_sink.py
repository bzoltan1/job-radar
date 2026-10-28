"""Telegram bot notification sink plugin."""

import html
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

from radar.models import Job
from radar.sinks.base import BaseSink

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/telegram_acp_bot/config.json")
DEFAULT_CHAT_ID = <chat_id>


def get_telegram_creds() -> Tuple[Optional[str], Optional[int]]:
    """Retrieve Telegram bot token and chat ID from environment or config file."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token and os.path.exists(DEFAULT_CONFIG_PATH):
        try:
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            token = cfg.get("telegram", {}).get("bot_token")
        except Exception:
            pass

    if not chat_id:
        chat_id = DEFAULT_CHAT_ID

    return token, int(chat_id) if chat_id else None


def send_telegram_message(text: str, token: Optional[str] = None, chat_id: Optional[int] = None) -> bool:
    """Send HTML message via Telegram Bot API."""
    t, c = get_telegram_creds()
    token = token or t
    chat_id = chat_id or c

    if not token or not chat_id:
        print("[-] Telegram notification skipped: No bot token or chat ID found.", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("ok", False)
    except Exception as e:
        print(f"[-] Error sending Telegram message: {e}", file=sys.stderr)
        return False


def format_jobs_html(jobs: List[Job], header: Optional[str] = None) -> str:
    """Format job list into clean Telegram HTML message."""
    count = len(jobs)
    lines = []
    if header:
        lines.append(f"<b>{html.escape(header)}</b>\n")
    else:
        lines.append(f"🎯 <b>Job Radar: {count} New Top Matches</b>\n")

    for j in jobs[:8]:
        comp = html.escape(j.company_id.capitalize())
        title = html.escape(j.title)
        loc = html.escape(j.location)
        url = j.url
        score = j.score
        match_pct = j.profile.match_pct
        sal = html.escape(j.salary.display or "")
        skills = html.escape(", ".join(j.profile.matched_skills))

        lines.append(f"⚡ <b>[{score} pts | {match_pct}% match] {comp}</b>")
        lines.append(f"  <a href=\"{url}\">{title}</a>")
        meta_line = f"  📍 {loc}"
        if sal and sal != "None":
            meta_line += f" | 💰 <b>{sal}</b>"
        lines.append(meta_line)
        if skills:
            lines.append(f"  🛠️ <code>{skills}</code>")
        lines.append("")

    if count > 8:
        lines.append(f"<i>...and {count - 8} more roles in Obsidian.</i>")

    return "\n".join(lines).strip()


class TelegramSink(BaseSink):
    name = "telegram"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        if not jobs:
            return

        min_score = context.get("min_score", 95)
        force = context.get("force_notify", False)
        conn = context.get("db_conn")

        eligible_jobs = []
        for j in jobs:
            if j.score >= min_score or j.salary.norm_max_eur >= 150000:
                if force:
                    eligible_jobs.append(j)
                elif conn:
                    row = conn.execute("SELECT notified_at FROM jobs WHERE id = ?", (j.id,)).fetchone()
                    if row and row["notified_at"] is None:
                        eligible_jobs.append(j)
                else:
                    eligible_jobs.append(j)

        if not eligible_jobs:
            return

        msg = format_jobs_html(eligible_jobs)
        ok = send_telegram_message(msg)
        if ok:
            print(f"[+] Dispatched Telegram alert for {len(eligible_jobs)} roles.")
            if conn:
                from radar.db import mark_notified
                mark_notified(conn, [j.id for j in eligible_jobs])
