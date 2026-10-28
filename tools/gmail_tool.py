"""
Gmail tool: lets the agent read/search your inbox.
Read-only scope on purpose (Stage 1) — it cannot send, delete, or modify anything.
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config


def _get_gmail_service():
    creds = None
    if os.path.exists(config.GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            config.GMAIL_TOKEN_FILE, config.GMAIL_SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Token revoked or expired — remove stale file and re-auth below.
                os.remove(config.GMAIL_TOKEN_FILE)
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(config.GMAIL_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Missing {config.GMAIL_CREDENTIALS_FILE}. "
                    "Download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.GMAIL_CREDENTIALS_FILE, config.GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(config.GMAIL_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _extract_snippet(msg):
    return {
        "id": msg["id"],
        "subject": next(
            (h["value"] for h in msg["payload"]["headers"] if h["name"] == "Subject"),
            "(no subject)",
        ),
        "from": next(
            (h["value"] for h in msg["payload"]["headers"] if h["name"] == "From"),
            "(unknown sender)",
        ),
        "snippet": msg.get("snippet", ""),
    }


def get_recent_emails(max_results=10, query="is:unread"):
    """
    Fetch recent emails. Default: unread only.
    query examples: 'is:unread', 'newer_than:1d', 'from:someone@example.com'
    """
    service = _get_gmail_service()
    results = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max_results, q=query)
        .execute()
    )
    messages = results.get("messages", [])

    emails = []
    for m in messages:
        msg = service.users().messages().get(userId="me", id=m["id"]).execute()
        emails.append(_extract_snippet(msg))
    return emails


if __name__ == "__main__":
    # quick manual test: python tools/gmail_tool.py
    for e in get_recent_emails():
        print(e["from"], "-", e["subject"])
