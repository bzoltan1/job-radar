"""Telegram bot notification sink plugin."""

import html
import json
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

from radar.config import get_telegram_config
from radar.models import Job
from radar.sinks.base import BaseSink


def get_telegram_creds() -> Tuple[Optional[str], Optional[int]]:
    """Retrieve Telegram bot token and chat ID from configuration or environment."""
    cfg = get_telegram_config()
    return cfg.get("bot_token"), cfg.get("chat_id")


def send_telegram_message(text: str, token: Optional[str] = None, chat_id: Optional[int] = None) -> bool:
    """Send HTML message via Telegram Bot API."""
    cfg_token, cfg_chat = get_telegram_creds()
    token = token or cfg_token
    chat_id = chat_id or cfg_chat

    if not token or not chat_id:
        print("[-] Telegram notification skipped: No bot token or chat ID found in environment or config.", file=sys.stderr)
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

    for j in jobs:
        comp = html.escape(j.company_id.capitalize())
        title = html.escape(j.title)
        loc = html.escape(j.location)
        url = html.escape(j.url, quote=True)
        score = j.score
        match_pct = j.profile.match_pct
        sal = html.escape(j.salary.display or "")
        skills = html.escape(", ".join(j.profile.matched_skills))

        lines.append(f"⚡ <b>[{score} pts | {match_pct}% match] {comp}</b>")
        lines.append(f'  <a href="{url}">{title}</a>')
        meta_line = f"  📍 {loc}"
        if sal and sal != "None":
            meta_line += f" | 💰 <b>{sal}</b>"
        lines.append(meta_line)
        if skills:
            lines.append(f"  🛠️ <code>{skills}</code>")
        lines.append("")

    return "\n".join(lines).strip()


CHUNK_SIZE = 8  # shortcut: sized by job count, not the 4096-char Telegram limit; split by length if titles get huge


def send_jobs(jobs: List[Job], token: Optional[str] = None, chat_id: Optional[int] = None) -> List[Job]:
    """Send jobs best-score-first in chunks; return the jobs whose chunk was delivered."""
    ranked = sorted(jobs, key=lambda j: j.score, reverse=True)
    sent: List[Job] = []
    for i in range(0, len(ranked), CHUNK_SIZE):
        chunk = ranked[i:i + CHUNK_SIZE]
        if not send_telegram_message(format_jobs_html(chunk), token=token, chat_id=chat_id):
            break
        sent.extend(chunk)
    return sent


class TelegramSink(BaseSink):
    name = "telegram"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        if not jobs:
            return

        tg_cfg = get_telegram_config()
        min_score = context.get("min_score")
        if min_score is None:
            min_score = tg_cfg["min_score"]
        if min_score is None:
            print("[-] Telegram: no score threshold (--notify-min-score or JOB_RADAR_NOTIFY_MIN_SCORE); skipping.", file=sys.stderr)
            return

        min_salary = tg_cfg["min_salary"]
        force = context.get("force_notify", False)
        conn = context.get("db_conn")

        eligible_jobs = []
        for j in jobs:
            # Drop jobs locked to foreign EU countries that don't hire in the configured country
            if any("loc:foreign_restriction" in t for t in j.tags):
                continue

            # Drop jobs without technical or profile qualification
            # (prevents company tier/entity bonuses + freshness from triggering alerts on non-technical roles)
            has_tech_relevance = (
                bool(j.profile and j.profile.match_pct > 0)
                or any(t.startswith(("role:", "tech:", "semantic:")) for t in j.tags)
            )
            if not has_tech_relevance:
                continue

            if j.score >= min_score or (min_salary is not None and j.salary.norm_max_eur and j.salary.norm_max_eur >= min_salary):
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

        sent = send_jobs(eligible_jobs)
        if sent:
            print(f"[+] Dispatched Telegram alert for {len(sent)}/{len(eligible_jobs)} roles.")
            if conn:
                from radar.db import mark_notified
                mark_notified(conn, [j.id for j in sent])
