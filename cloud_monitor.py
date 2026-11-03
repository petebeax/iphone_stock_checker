"""GitHub Actions monitoring from a cloud-only JSON secret.

WATCHLIST_JSON can contain simple entries with model/storage/color/location/email.
The Apple part number is resolved dynamically from Apple's catalog.
Previously exported full watch records remain supported.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL

from monitor import main as monitor_main
from stock_core import family_for_model, get_catalog
from watchlist import DATA_DIR, WATCHLIST_PATH

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / 'cloud_state.json'
BACKOFF = DATA_DIR / 'apple_backoff_until.txt'


def prepare_watches(config: list[dict], *, catalog_loader=get_catalog) -> list[dict]:
    if not isinstance(config, list) or not config:
        raise ValueError('WATCHLIST_JSON must be a nonempty JSON array')
    catalog = None
    watches = []
    for index, entry in enumerate(config, 1):
        if not isinstance(entry, dict):
            raise ValueError(f'Alert {index} must be a JSON object')
        item = dict(entry)
        for field in ('model', 'location', 'email'):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f'Alert {index}: missing {field}')
            item[field] = item[field].strip()
        if not item.get('part'):
            for field in ('storage', 'color'):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    raise ValueError(f'Alert {index}: missing {field}')
                item[field] = item[field].strip()
            if catalog is None:
                catalog = catalog_loader()
            matches = [variant for variant in catalog if all(
                str(variant.get(field, '')).casefold() == item[field].casefold()
                for field in ('model', 'storage', 'color')
            )]
            if len(matches) != 1:
                choices = sorted({
                    f"{v['model']} / {v['storage']} / {v['color']}"
                    for v in catalog if str(v.get('model', '')).casefold() == item['model'].casefold()
                })
                raise ValueError(
                    f"Alert {index}: configuration not found or ambiguous in Apple's current catalog. "
                    f"Available options for that model: {choices[:30]}"
                )
            item['part'] = matches[0]['part']
            item['family'] = family_for_model(item['model'])
        else:
            if not item.get('family'):
                item['family'] = family_for_model(item['model'])
        item['target_stores'] = item.get('target_stores', [])
        if not isinstance(item['target_stores'], list):
            raise ValueError(f'Alert {index}: target_stores must be an array')
        item['sms'] = item.get('sms', '')
        # Stable ID ensures dedup state survives the next runner, and changes when config changes.
        item['id'] = item.get('id') or uuid5(NAMESPACE_URL, json.dumps({
            key: item.get(key) for key in ('model', 'storage', 'color', 'location', 'email', 'sms', 'target_stores')
        }, sort_keys=True)).hex
        watches.append(item)
    return watches


def run() -> int:
    raw = os.environ.get('WATCHLIST_JSON', '').strip()
    if not raw:
        raise RuntimeError('Missing WATCHLIST_JSON GitHub Actions secret')
    watches = prepare_watches(json.loads(raw))
    state = json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    if not isinstance(state, dict):
        raise ValueError('cloud_state.json must be an object')
    saved = state.get('notified', {})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for item in watches:
        previous = saved.get(item['id'], {})
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
    if new_state != state:
        STATE_PATH.write_text(json.dumps(new_state, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print('Cloud alert state updated')
    else:
        print('Cloud alert state unchanged')
    return result


if __name__ == '__main__':
    raise SystemExit(run())
