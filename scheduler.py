"""
Background job: periodically checks your inbox and pings you on Telegram
ONLY if something looks important. This is what makes it "proactive"
instead of just answering when asked.

To save Gemini quota, each run:
  1. Only asks Gmail for unread mail outside Promotions/Social/Forums.
  2. Skips obvious automated senders (no-reply, newsletters) without
     calling the AI at all.
  3. Remembers every email it has already judged (seen_emails.json),
     so nothing is judged or notified twice.
  4. Judges at most MAX_AI_CALLS_PER_RUN emails per run and stops
     immediately if Gemini says we're rate-limited.

Run this alongside bot.py (separate process) or via main.py on Render.
"""
import asyncio
import json
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from openai import RateLimitError
from telegram import Bot

import config
from tools.gmail_tool import get_recent_emails
from agent import client as llm_client  # reuse the same Gemini client

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
_telegram_loop = None

# --- Tunables ---------------------------------------------------------
MAIL_QUERY = "is:unread -category:promotions -category:social -category:forums"
MAX_EMAILS_PER_RUN = 10
MAX_AI_CALLS_PER_RUN = 5      # hard cap on Gemini calls per run
SECONDS_BETWEEN_AI_CALLS = 4  # stays under per-minute limits
SEEN_FILE = Path(__file__).resolve().parent / "seen_emails.json"
MAX_SEEN_IDS = 500            # keep the file small

# Senders containing any of these are skipped with no AI call.
JUNK_SENDER_HINTS = (
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "newsletter", "notifications@", "notification@", "marketing",
    "promo", "offers@", "deals@", "mailer", "updates@", "digest",
)


# --- Telegram ---------------------------------------------------------
def _get_telegram_loop():
    global _telegram_loop
    if _telegram_loop is None or _telegram_loop.is_closed():
        _telegram_loop = asyncio.new_event_loop()
    return _telegram_loop


def _send_telegram(text):
    loop = _get_telegram_loop()
    loop.run_until_complete(bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=text))


# --- Remembering what we've already handled ---------------------------
def _load_seen():
    try:
        return json.loads(SEEN_FILE.read_text())
    except (OSError, ValueError):
        return []


def _save_seen(seen_ids):
    try:
        SEEN_FILE.write_text(json.dumps(seen_ids[-MAX_SEEN_IDS:]))
    except OSError as e:
        # Read-only or ephemeral disk: not fatal, we may just re-check
        # a few emails after a restart.
        print(f"Could not save seen emails: {e}")


# --- Judging importance -----------------------------------------------
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


def looks_like_junk(email):
    sender = email["from"].lower()
    return any(hint in sender for hint in JUNK_SENDER_HINTS)


def is_important(email):
    """Asks Gemini. May raise RateLimitError - the caller handles that."""
    prompt = IMPORTANCE_PROMPT.format(
        sender=email["from"], subject=email["subject"], snippet=email["snippet"]
    )
    response = llm_client.chat.completions.create(
        model=config.GEMINI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    verdict = (response.choices[0].message.content or "").strip().upper()
    return verdict.startswith("IMPORTANT")


# --- The job ----------------------------------------------------------
def check_mail_job():
    print("Checking mail...")
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("Skipping mail check: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        return

    try:
        emails = get_recent_emails(max_results=MAX_EMAILS_PER_RUN, query=MAIL_QUERY)
    except Exception as e:
        print(f"Mail check failed: {e}")
        return

    seen = _load_seen()
    seen_set = set(seen)
    ai_calls = 0
    notified = 0

    for email in emails:
        if email["id"] in seen_set:
            continue

        # 1) Obvious automated mail: skip without spending an AI call.
        if looks_like_junk(email):
            seen.append(email["id"])
            seen_set.add(email["id"])
            continue

        # 2) Respect the per-run AI budget; the rest wait for next run.
        if ai_calls >= MAX_AI_CALLS_PER_RUN:
            print("AI call limit for this run reached; the rest wait for next run.")
            break

        try:
            if ai_calls > 0:
                time.sleep(SECONDS_BETWEEN_AI_CALLS)
            ai_calls += 1
            important = is_important(email)
        except RateLimitError:
            # Don't mark as seen - retry on the next run.
            print("Gemini rate limit hit; stopping this run, will retry next time.")
            break
        except Exception as e:
            print(f"Could not judge email {email.get('id', '?')}: {e}")
            continue

        if important:
            try:
                _send_telegram(
                    f"📬 Important email:\n"
                    f"From: {email['from']}\n"
                    f"Subject: {email['subject']}\n"
                    f"{email['snippet']}"
                )
                notified += 1
            except Exception as e:
                # Telegram failed: leave unseen so we try again next run.
                print(f"Failed to notify for email {email['id']}: {e}")
                continue

        seen.append(email["id"])
        seen_set.add(email["id"])

    _save_seen(seen)
    print(f"Done. AI calls: {ai_calls}, notifications sent: {notified}.")


def main():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_mail_job,
        "interval",
        minutes=config.MAIL_CHECK_INTERVAL_MINUTES,
        max_instances=1,
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