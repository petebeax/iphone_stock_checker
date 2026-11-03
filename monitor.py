"""Run once from Task Scheduler (or manually) to check saved iPhone alerts.

Usage: python monitor.py
Checks every watch, sends at most one alert per store while stock remains
available, and rearms alerts only when a store explicitly becomes unavailable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys

import requests

from notifications import send_email, send_sms
from stock_core import check_pickup, buy_url
from watchlist import (
    DATA_DIR, clear_sold_out, file_lock, load_watches, pending_for_channel,
    relevant_rows, update_watch_state,
)


def alert_content(watch: dict, matches: list[dict]) -> tuple[str, str]:
    model = " ".join(part for part in (watch["model"], watch["storage"], watch["color"]) if part)
    stores = ", ".join(f"{r['Store']} ({r['City']})" for r in matches)
    subject = f"iPhone available: {model}"
    body = (
        f"Apple Store pickup is currently listed as available.\n\n"
        f"Configuration: {model}\n"
        f"Part number: {watch['part']}\n"
        f"Search area: {watch['location']}\n"
        f"Stores: {stores}\n\n"
        f"Verify pickup availability at Apple checkout: {buy_url(watch['family'])}\n\n"
        "Availability can change quickly. This is not a reservation."
    )
    return subject, body


def check_watch(watch: dict) -> tuple[int, list[str]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    notified = watch.get("notified") or {"email": [], "sms": []}
    try:
        stores, checked = check_pickup(watch["part"], watch["location"], watch["family"])
        if not stores:
            raise RuntimeError("No stores returned; existing alert state was preserved")
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        update_watch_state(watch["id"], notified, now, str(exc))
        return 0, [f"{watch['model']}: check failed: {exc}"]

    scoped = relevant_rows(watch, stores)
    notified = clear_sold_out(notified, scoped)
    count = 0
    messages = []
    for channel in ("email", "sms"):
        recipient = watch.get(channel, "")
        if not recipient:
            continue
        pending = pending_for_channel(channel, notified, scoped)
        if not pending:
            continue
        subject, body = alert_content(watch, pending)
        try:
            if channel == "email":
                send_email(recipient, subject, body)
            else:
                send_sms(recipient, body)
            notified[channel] = sorted(set(notified.get(channel, [])) | {r["Store ID"] for r in pending})
            count += 1
            messages.append(f"{watch['model']}: {channel} alert accepted for {len(pending)} store(s)")
        except Exception as exc:  # Don't block a successful other channel.
            messages.append(f"{watch['model']}: {channel} alert failed: {exc}")
    error = "; ".join(m for m in messages if "failed:" in m)
    update_watch_state(watch["id"], notified, checked, error)
    if not messages:
        messages.append(f"{watch['model']}: checked {len(scoped)} store(s); nothing new to report")
    return count, messages


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backoff_path = DATA_DIR / "apple_backoff_until.txt"
    if backoff_path.exists():
        try:
            until = datetime.fromisoformat(backoff_path.read_text(encoding="utf-8").strip())
            if datetime.now(timezone.utc) < until:
                print(f"Skipping checks because Apple recently rate-limited us; resume after {until.isoformat()}")
                return 0
        except (OSError, ValueError):
            pass
    try:
        # Prevent overlapping scheduled runs (and duplicate sends).
        with file_lock(DATA_DIR / ".monitor.lock", stale_seconds=1800, attempts=1):
            watches = load_watches()
            if not watches:
                print("No alerts saved. Add an alert in the Streamlit app first.")
                return 0
            total = 0
            for watch in watches:
                count, messages = check_watch(watch)
                total += count
                for message in messages:
                    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}")
                if any("rate-limited" in m.lower() for m in messages):
                    until = datetime.now(timezone.utc) + timedelta(minutes=30)
                    backoff_path.write_text(until.isoformat(), encoding="utf-8")
                    print("Apple rate limit detected; pausing all monitoring checks for 30 minutes.")
                    break
            print(f"Finished: {len(watches)} watch(es), {total} notification(s) accepted")
            return 0
    except RuntimeError as exc:
        if "being updated by another process" in str(exc):
            print("Monitor already running; skipped this overlapping invocation.")
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
