"""Send test email to one or all unique recipients from the cloud watchlist.

Test modes do not query Apple or modify alert history.
"""
from __future__ import annotations

import argparse

from notifications import email_valid, send_email
from secure_watchlist import load_cloud_watchlist

SUBJECT = "iPhone Stock Checker — GitHub test email"
BODY = ("This is a test email from your GitHub Actions iPhone Stock Checker. "
        "Email sending was attempted; no iPhone availability was checked.")


def unique_recipients(watches: list[dict]) -> list[str]:
    """Return one address per unique email (case-insensitive), preserving order."""
    recipients: list[str] = []
    seen: set[str] = set()
    for watch in watches:
        if not isinstance(watch, dict):
            continue
        value = watch.get("email")
        if not isinstance(value, str):
            continue
        recipient = value.strip()
        if not email_valid(recipient):
            continue
        key = recipient.casefold()
        if key not in seen:
            seen.add(key)
            recipients.append(recipient)
    return recipients


def main() -> None:
    parser = argparse.ArgumentParser(description="Send GitHub Actions test email(s)")
    parser.add_argument("--all", action="store_true", dest="all_emails",
                        help="Send one test email to every unique watchlist recipient")
    args = parser.parse_args()

    recipients = unique_recipients(load_cloud_watchlist())
    if not recipients:
        raise RuntimeError("No valid email recipients found in cloud watchlist")
    if not args.all_emails:
        recipients = recipients[:1]

    failures = 0
    for index, recipient in enumerate(recipients, 1):
        try:
            send_email(recipient, SUBJECT, BODY)
            # Avoid printing addresses in publicly accessible GitHub Actions logs.
            print(f"Test email {index}/{len(recipients)} accepted by SMTP")
        except Exception as exc:
            failures += 1
            # Do not print exception text: it may contain credentials or PII.
            print(f"Test email {index}/{len(recipients)} failed ({type(exc).__name__})")

    print(f"Email test complete: {len(recipients) - failures}/{len(recipients)} accepted by SMTP")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
