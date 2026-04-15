"""PAM Email — send emails via Gmail SMTP."""

import json
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from app.config import EMAIL_CREDENTIALS_FILE

_credentials: dict | None = None
_loaded = False


def load_credentials() -> dict | None:
    """Load email credentials from JSON file. Returns None if not configured."""
    global _credentials, _loaded
    if _loaded:
        return _credentials
    _loaded = True
    try:
        if EMAIL_CREDENTIALS_FILE.exists():
            _credentials = json.loads(EMAIL_CREDENTIALS_FILE.read_text())
        else:
            print("[PAM] Email not configured — no credentials file found")
    except Exception as e:
        print(f"[PAM] Failed to load email credentials: {e}")
    return _credentials


def is_configured() -> bool:
    """Check if email credentials are available."""
    return load_credentials() is not None


async def send_email(subject: str, body_html: str, body_text: str | None = None) -> bool:
    """Send an email from PAM's Gmail account.

    Returns True if sent successfully, False otherwise.
    Silently no-ops if email is not configured.
    """
    creds = load_credentials()
    if not creds:
        return False

    from app.services.settings import get_setting
    sender = creds["email"]
    override = (await get_setting("briefing_email_recipient", "")).strip()
    recipient = override or creds["recipient"]
    app_password = creds["app_password"]

    msg = EmailMessage()
    msg["From"] = f"PAM <{sender}>"
    msg["To"] = recipient
    msg["Subject"] = subject

    if body_text:
        msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(body_html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname="smtp.gmail.com",
            port=587,
            start_tls=True,
            username=sender,
            password=app_password,
        )
        print(f"[PAM] Email sent: {subject}")
        return True
    except Exception as e:
        print(f"[PAM] Email send failed: {e}")
        return False
