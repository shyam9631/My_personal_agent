"""
Background job: periodically checks your inbox and pings you on Telegram
ONLY if something looks important. This is what makes it "proactive"
instead of just answering when asked.

Run this alongside bot.py (separate process) — e.g. in two terminals,
or as two services if you deploy it.
"""
import asyncio
import time
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot

import config
from tools.gmail_tool import get_recent_emails
from agent import client as groq_client  # reuse the same Groq client

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
_telegram_loop = None


def _get_telegram_loop():
    global _telegram_loop
    if _telegram_loop is None or _telegram_loop.is_closed():
        _telegram_loop = asyncio.new_event_loop()
    return _telegram_loop


def _send_telegram(text):
    loop = _get_telegram_loop()
    loop.run_until_complete(bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text))

IMPORTANCE_PROMPT = """You are filtering emails for importance for a
college student who also freelances.

Reply with ONLY "IMPORTANT" or "SKIP".

Mark IMPORTANT only for:
- A real person writing directly (not an automated/no-reply sender)
- College/exam/academic deadlines or results
- A client, job, or internship response that needs action
- Banking/payment issues that are genuinely account-specific (not generic offers)

Mark SKIP for:
- Anything from a no-reply, marketing, or notifications address
- Newsletters, promotions, discount codes, "expiring soon" offers, or
  subscription reminders - even if worded urgently. Manufactured urgency
  ("expiring soon", "don't miss out", "last chance") is a marketing
  tactic, not real urgency - treat it as SKIP.
- Social media notifications, LinkedIn digests, generic internship/job
  bulk mailers not addressed to a specific opportunity
- Anything that looks like phishing or a generic automated blast

When unsure, prefer SKIP - it's better to miss a borderline email than
to interrupt Shyam with noise.

Email:
From: {sender}
Subject: {subject}
Snippet: {snippet}
"""


def is_important(email):
    prompt = IMPORTANCE_PROMPT.format(
        sender=email["from"], subject=email["subject"], snippet=email["snippet"]
    )
    response = groq_client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    verdict = response.choices[0].message.content.strip().upper()
    return "IMPORTANT" in verdict


def check_mail_job():
    print("Checking mail...")
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("Skipping mail check: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return

    try:
        emails = get_recent_emails(max_results=10, query="is:unread")
    except Exception as e:
        print(f"Mail check failed: {e}")
        return

    for email in emails:
        try:
            if is_important(email):
                message = (
                    f"📬 Important email:\n"
                    f"From: {email['from']}\n"
                    f"Subject: {email['subject']}\n"
                    f"{email['snippet']}"
                )
                _send_telegram(message)
        except Exception as e:
            print(f"Failed to process or notify for email {email.get('id', '?')}: {e}")


def main():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_mail_job, "interval", minutes=config.MAIL_CHECK_INTERVAL_MINUTES
    )
    scheduler.start()
    print(
        f"Scheduler running, checking mail every {config.MAIL_CHECK_INTERVAL_MINUTES} min. Ctrl+C to stop."
    )
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()