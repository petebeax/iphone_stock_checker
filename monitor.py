"""Run once from Task Scheduler (or manually) to check saved iPhone alerts.

Usage: python monitor.py
Checks every watch, sends at most one alert per store while stock remains
available, and rearms alerts only when a store explicitly becomes unavailable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
import sys

import requests

from notifications import send_email, send_sms
from stock_core import check_pickup, buy_url
from watchlist import (
    DATA_DIR, clear_sold_out, file_lock, load_watches, pending_for_channel,
    relevant_rows, update_watch_state,
)


def alert_content(watch: dict, matches: list[dict]) -> tuple[str, str]:
    """Plain text for SMS and email fallback."""
    model = " ".join(str(p) for p in (watch.get("model"), watch.get("storage"), watch.get("color")) if p)
    lines = []
    for row in matches:
        store = str(row.get("Store") or "Apple Store")
        city = str(row.get("City") or "")
        distance = str(row.get("Distance") or "")
        details = str(row.get("Pickup details") or "")
        lines.append("- " + store + (f" ({city})" if city else "") +
                     (f" — {distance}" if distance else "") +
                     (f"\n  Pickup: {details}" if details else ""))
    subject = f"iPhone pickup available: {model} ({len(matches)} store{'s' if len(matches) != 1 else ''})"
    body = (f"Apple currently lists pickup availability for your selected iPhone.\n\n"
            f"{model}\nApple part number: {watch.get('part', '')}\n"
            f"Search area: {watch.get('location', '')}\n\n"
            f"AVAILABLE STORES ({len(matches)})\n" + "\n".join(lines) + "\n\n" +
            f"CHECK ON APPLE: {buy_url(watch['family'])}\n\n"
            "Availability may change before checkout. This is not a reservation.")
    return subject, body


def alert_html(watch: dict, matches: list[dict]) -> str:
    """Mobile-friendly HTML alternative. Escape all untrusted input."""
    from stock_core import secure_apple_link
    model = " ".join(str(p) for p in (watch.get("model"), watch.get("storage"), watch.get("color")) if p)
    safe_model = escape(model)
    safe_area = escape(str(watch.get("location") or ""))
    safe_part = escape(str(watch.get("part") or ""))
    safe_url = escape(buy_url(watch["family"]), quote=True)
    cards = []
    for row in matches:
        name = escape(str(row.get("Store") or "Apple Store"))
        city = escape(str(row.get("City") or ""))
        distance = escape(str(row.get("Distance") or ""))
        details = escape(str(row.get("Pickup details") or ""))
        trusted = secure_apple_link(str(row.get("Apple link") or ""))
        link = (f'<a href="{escape(trusted, quote=True)}" style="color:#167a47">Store details</a>' if trusted else "")
        meta = " · ".join(v for v in (city, distance) if v)
        details_line = f'<div style="font-size:13px;color:#4e5867;margin-top:5px">{details}</div>' if details else ''
        link_line = f'<div style="margin-top:7px">{link}</div>' if link else ''
        cards.append(f'<tr><td style="padding:14px 16px;border-bottom:1px solid #e8ecf0">'
                     f'<div style="font-weight:700;font-size:15px;color:#17212d">{name}</div>'
                     f'<div style="font-size:13px;color:#627083;margin-top:4px">{meta}</div>'
                     f'<div style="font-size:13px;color:#167a47;font-weight:600;margin-top:7px">Pickup available</div>'
                     f'{details_line}{link_line}</td></tr>')
    count = len(matches)
    plural = 's' if count != 1 else ''
    checked = datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;color:#17212d">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">Pickup available at {count} Apple Store(s) near {safe_area}.</div>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f4f6f9"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;background:#ffffff;border:1px solid #e7ebf0;border-radius:14px;overflow:hidden">
<tr><td style="padding:22px 24px 10px;font-size:13px;font-weight:700;letter-spacing:1px;color:#526174">IPHONE STOCK CHECKER</td></tr>
<tr><td style="padding:10px 24px 20px"><div style="color:#167a47;font-size:13px;font-weight:700">● PICKUP AVAILABLE</div>
<h1 style="font-size:25px;line-height:1.25;margin:9px 0 8px">{safe_model}</h1>
<p style="font-size:14px;color:#566273;line-height:1.6;margin:0">Available at <strong>{count} Apple Store{plural}</strong> near {safe_area}. Inventory can change quickly.</p>
<a href="{safe_url}" style="display:inline-block;margin-top:20px;background:#1669d1;border-radius:9px;padding:13px 19px;color:#ffffff;font-size:14px;font-weight:700;text-decoration:none">Check pickup on Apple →</a></td></tr>
<tr><td style="background:#f9fbfc;padding:17px 24px 7px;font-size:15px;font-weight:700">Available stores</td></tr>
<tr><td style="padding:0 24px 16px;background:#f9fbfc"><table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#fff;border:1px solid #e8ecf0;border-radius:9px">{''.join(cards)}</table></td></tr>
<tr><td style="padding:18px 24px 22px;color:#697588;font-size:12px;line-height:1.6">Part number: {safe_part}<br>Checked: {escape(checked)}<br>This is an automated stock alert, not a reservation. Confirm pickup availability directly with Apple before traveling.</td></tr>
</table></td></tr></table></body></html>'''


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
                send_email(recipient, subject, body, html_body=alert_html(watch, pending))
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
