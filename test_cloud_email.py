"""Send a GitHub Actions-only test email without querying Apple or altering alert state."""
from __future__ import annotations

import json
import os

from notifications import email_valid, send_email


def recipient_from_watchlist(raw: str) -> str:
    if not raw.strip():
        raise ValueError("WATCHLIST_JSON secret is missing")
    watchlist = json.loads(raw)
    if not isinstance(watchlist, list) or not watchlist:
        raise ValueError("WATCHLIST_JSON must contain at least one watch")
    for watch in watchlist:
        if isinstance(watch, dict):
            recipient = watch.get("email", "")
            if isinstance(recipient, str) and email_valid(recipient.strip()):
                return recipient.strip()
    raise ValueError("No valid email recipient found in WATCHLIST_JSON")


def main() -> None:
    recipient = recipient_from_watchlist(os.getenv("WATCHLIST_JSON", ""))
    send_email(
        recipient,
        "iPhone Stock Checker — GitHub test email",
        "This is a test email from your GitHub Actions iPhone Stock Checker. "
        "Email sending succeeded; no iPhone availability was checked."
    )
    print("Test email accepted by Gmail SMTP. Check the recipient inbox and spam folder.")


if __name__ == "__main__":
    main()
