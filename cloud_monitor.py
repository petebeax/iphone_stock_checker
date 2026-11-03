"""GitHub Actions bridge: watch configuration from a secret; dedup state in Git.

WATCHLIST_JSON must contain the list created by the local Streamlit app.
No email addresses or SMTP credentials are saved in cloud_state.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

from monitor import main as monitor_main
from watchlist import DATA_DIR, WATCHLIST_PATH

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / 'cloud_state.json'
BACKOFF = DATA_DIR / 'apple_backoff_until.txt'


def run() -> int:
    raw = os.environ.get('WATCHLIST_JSON', '').strip()
    if not raw:
        raise RuntimeError('Missing WATCHLIST_JSON GitHub Actions secret')
    watches = json.loads(raw)
    if not isinstance(watches, list) or not watches:
        raise ValueError('WATCHLIST_JSON must contain a nonempty JSON list of saved alerts')
    for item in watches:
        if not isinstance(item, dict) or not all(item.get(k) for k in ('id', 'part', 'location', 'family', 'model')):
            raise ValueError('Invalid alert: missing required fields')
    state = json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    if not isinstance(state, dict):
        raise ValueError('cloud_state.json must be an object')
    saved = state.get('notified', {})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for item in watches:
        previous = saved.get(item['id'], {})
        # Deduplication must be restored from last run, not from the user-supplied snapshot.
        item['notified'] = {
            channel: previous.get(channel, []) if isinstance(previous, dict) else []
            for channel in ('email', 'sms')
        }
    WATCHLIST_PATH.write_text(json.dumps(watches), encoding='utf-8')
    if state.get('backoff_until'):
        BACKOFF.write_text(state['backoff_until'], encoding='utf-8')
    else:
        BACKOFF.unlink(missing_ok=True)

    result = monitor_main()
    updated = json.loads(WATCHLIST_PATH.read_text(encoding='utf-8'))
    new_state = {
        'notified': {w['id']: w.get('notified', {'email': [], 'sms': []}) for w in updated},
    }
    if BACKOFF.exists():
        until = BACKOFF.read_text(encoding='utf-8').strip()
        try:
            if datetime.fromisoformat(until) > datetime.now(timezone.utc):
                new_state['backoff_until'] = until
        except ValueError:
            pass
    # Do not commit needless timestamp changes every 5 minutes.
    if new_state != state:
        STATE_PATH.write_text(json.dumps(new_state, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print('Cloud alert state updated')
    else:
        print('Cloud alert state unchanged')
    return result


if __name__ == '__main__':
    raise SystemExit(run())
