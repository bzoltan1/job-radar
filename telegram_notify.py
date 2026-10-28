#!/usr/bin/env python3
"""Job Radar: Telegram Notification Dispatcher."""

import argparse
import html
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/telegram_acp_bot/config.json")
DEFAULT_CHAT_ID = <chat_id>


def get_telegram_creds():
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


def send_message(text: str, token: str = None, chat_id: int = None, parse_mode: str = "HTML") -> bool:
    if not token or not chat_id:
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
        "parse_mode": parse_mode,
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


def format_jobs_html(jobs, header: str = None) -> str:
    count = len(jobs)
    lines = []
    if header:
        lines.append(f"<b>{html.escape(header)}</b>\n")
    else:
        lines.append(f"🎯 <b>Job Radar: {count} New Top Matches</b>\n")

    for j in jobs[:8]:
        comp = html.escape(str(j.get("company_name") or j.get("company_id", "")).capitalize())
        title = html.escape(str(j.get("title", "")))
        loc = html.escape(str(j.get("location", "")))
        url = j.get("url", "")
        score = j.get("score", 0)
        match_pct = j.get("profile_match_pct") or 0
        sal = html.escape(str(j.get("salary_display") or ""))
        skills = html.escape(str(j.get("matched_skills") or ""))

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


def notify_new_jobs(jobs, token: str = None, chat_id: int = None) -> bool:
    if not jobs:
        return True
    text = format_jobs_html(jobs)
    return send_message(text, token=token, chat_id=chat_id)


def main():
    parser = argparse.ArgumentParser(description="Send Job Radar alerts via Telegram")
    parser.add_argument("message", nargs="?", default="", help="Custom message text to send")
    parser.add_argument("--test", action="store_true", help="Send a test ping to verify Telegram connectivity")
    parser.add_argument("--token", default=None, help="Telegram bot token")
    parser.add_argument("--chat-id", type=int, default=None, help="Target Telegram chat ID")

    args = parser.parse_args()
    if args.test:
        ok = send_message("🤖 <b>Job Radar</b>: Telegram bot alert connection verified.", token=args.token, chat_id=args.chat_id)
        if ok:
            print("[+] Telegram test message delivered successfully.")
        else:
            sys.exit(1)
    elif args.message:
        send_message(args.message, token=args.token, chat_id=args.chat_id)


if __name__ == "__main__":
    main()
