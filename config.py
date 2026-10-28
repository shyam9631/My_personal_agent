"""
Central place for all API keys / settings.
Reads from a .env file (never commit this file with real keys to GitHub).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
# Get this from @BotFather on Telegram (free, takes 2 minutes)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Your personal Telegram chat ID (the bot only messages YOU, not the public)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Meta WhatsApp Cloud API ---
# From developers.facebook.com -> your app -> WhatsApp -> API Setup
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
# Any string you make up yourself - used to verify the webhook with Meta
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
# Your own WhatsApp number in international format, no + or spaces, e.g. 919876543210
META_RECIPIENT_NUMBER = os.getenv("META_RECIPIENT_NUMBER", "")

# --- Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# --- Gmail ---
# credentials.json downloaded from Google Cloud Console (OAuth client, Desktop app type)
# Locally these are just files in the project folder. On Render, these paths
# point to Render's "Secret Files" instead (see RENDER_DEPLOY.md).
GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# --- Scheduler ---
# How often (minutes) the background job checks your inbox
MAIL_CHECK_INTERVAL_MINUTES = 15