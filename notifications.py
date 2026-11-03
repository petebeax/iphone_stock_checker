"""Send notifications to explicitly configured recipients only.

Credentials are read from .env, never from saved watch entries.
"""

from __future__ import annotations

from email.message import EmailMessage
import os
import re
import smtplib
import ssl
from pathlib import Path

from dotenv import load_dotenv
import requests

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def email_valid(value: str) -> bool:
    return bool(re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value)) and len(value) <= 254


def phone_valid(value: str) -> bool:
    return bool(re.fullmatch(r"\+[1-9]\d{7,14}", value))


def configured_channels() -> dict[str, bool]:
    env = os.environ
    return {
        "email": all(env.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")),
        "sms": all(env.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")),
    }


def send_email(recipient: str, subject: str, body: str, *, html_body: str | None = None) -> None:
    if not email_valid(recipient):
        raise ValueError("Enter a valid notification email address")
    if not configured_channels()["email"]:
        raise RuntimeError("SMTP credentials are missing from .env")
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    sender = os.getenv("EMAIL_FROM") or user
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(user, os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
    elif port == 587:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(user, os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
    else:
        raise ValueError("Use SMTP port 587 (STARTTLS) or 465 (SSL)")


def send_sms(recipient: str, body: str) -> None:
    if not phone_valid(recipient):
        raise ValueError("Use international phone format, e.g. +14165550123")
    if not configured_channels()["sms"]:
        raise RuntimeError("Twilio credentials are missing from .env")
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    response = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
        data={"From": os.environ["TWILIO_FROM"], "To": recipient, "Body": body},
        timeout=20,
    )
    if response.status_code not in (200, 201):
        # Deliberately omit provider response: it could include phone numbers or account data.
        raise RuntimeError(f"Twilio rejected the SMS request (HTTP {response.status_code})")


def send_test(channel: str, recipient: str) -> None:
    subject = "iPhone Stock Checker — test notification"
    body = "This is a test notification from your local iPhone Stock Checker. No inventory alert has occurred."
    if channel == "email":
        send_email(recipient, subject, body)
    elif channel == "sms":
        send_sms(recipient, body)
    else:
        raise ValueError("Unknown notification channel")
