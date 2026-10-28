"""
Single entry point for deploying to Render's free tier.

Render's free plan only keeps "web services" alive (and even those sleep
after 15 min with no HTTP traffic). To use the free tier for a Telegram
bot (which doesn't receive HTTP traffic itself), this file:

1. Runs a tiny Flask web server with a "/" route - this is what Render
   pings to consider the service "alive", and what a free external
   pinger (UptimeRobot) will hit every few minutes to prevent sleep.
2. Runs the Telegram bot (polling) in a background thread.
3. Runs the mail-check scheduler in another background thread.

Locally, you can still run bot.py and scheduler.py separately if you
prefer - this file is specifically for the Render deployment.
"""
import os
import threading
import logging
from flask import Flask

import config
from bot import main as run_telegram_bot
from scheduler import main as run_scheduler

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)


@app.route("/")
def health_check():
    return "Personal assistant is alive.", 200


def start_background_jobs():
    # Telegram bot polling needs its own thread since it blocks forever
    telegram_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    telegram_thread.start()

    # Scheduler also runs forever (its own loop) - same idea
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()


# Started at import time (not inside __main__) so this also runs correctly
# under gunicorn on Render, which imports this file as "main:app" and never
# executes the __main__ block below.
start_background_jobs()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)