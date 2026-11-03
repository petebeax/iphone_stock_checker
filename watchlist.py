"""Local watchlist persistence and availability transition helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"


@contextmanager
def file_lock(path: Path, *, stale_seconds: int = 300, attempts: int = 50):
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(attempts):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale_seconds:
                    path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            time.sleep(0.1)
    else:
        raise RuntimeError("Watchlist is being updated by another process; try again shortly")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _read() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Saved watchlist is not a list")
    return data


def _write(watches: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / f"watchlist.{uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(watches, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, WATCHLIST_PATH)
    finally:
        tmp.unlink(missing_ok=True)


def load_watches() -> list[dict]:
    return _read()


def create_watch(
    *, part: str, model: str, storage: str, color: str,
    location: str, family: str, target_stores: list[str],
    email: str = "", sms: str = "",
) -> dict:
    watch = {
        "id": uuid4().hex,
        "part": part, "model": model, "storage": storage, "color": color,
        "location": location.strip(), "family": family,
        "target_stores": sorted(set(target_stores)),
        "email": email.strip(), "sms": sms.strip(),
        "notified": {"email": [], "sms": []},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_checked": "", "last_error": "",
    }
    with file_lock(DATA_DIR / ".watchlist.lock"):
        watches = _read()
        signature = (part, location.strip().casefold(), sorted(set(target_stores)), email.strip(), sms.strip())
        for existing in watches:
            if (existing["part"], existing["location"].casefold(), existing.get("target_stores", []),
                existing.get("email", ""), existing.get("sms", "")) == signature:
                raise ValueError("This exact alert is already saved")
        watches.append(watch)
        _write(watches)
    return watch


def delete_watch(watch_id: str) -> None:
    with file_lock(DATA_DIR / ".watchlist.lock"):
        _write([w for w in _read() if w["id"] != watch_id])


def update_watch_state(watch_id: str, notified: dict, checked: str, error: str) -> None:
    with file_lock(DATA_DIR / ".watchlist.lock"):
        watches = _read()
        for w in watches:
            if w["id"] == watch_id:
                w["notified"] = notified
                w["last_checked"] = checked
                w["last_error"] = error
                break
        else:
            return  # Removed while the monitor was checking: do not recreate it.
        _write(watches)


def relevant_rows(watch: dict, stores: list[dict]) -> list[dict]:
    targets = set(watch.get("target_stores", []))
    return [s for s in stores if not targets or s["Store ID"] in targets]


def clear_sold_out(notified: dict, stores: list[dict]) -> dict:
    """Reset alert eligibility only on explicit 'Unavailable', not Unknown/omitted."""
    sold_out = {r["Store ID"] for r in stores if r["Status"] == "Unavailable"}
    return {
        channel: [sid for sid in notified.get(channel, []) if sid not in sold_out]
        for channel in ("email", "sms")
    }


def pending_for_channel(channel: str, notified: dict, stores: list[dict]) -> list[dict]:
    sent = set(notified.get(channel, []))
    return [r for r in stores if r["Status"] == "Available" and r["Store ID"] not in sent]
