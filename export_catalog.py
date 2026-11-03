"""Publish non-sensitive product variants for the GitHub Pages editor."""
import json
from pathlib import Path
from stock_core import get_catalog


def main():
    path = Path(__file__).resolve().parent / 'catalog.json'
    try:
        variants = get_catalog()
    except Exception as exc:
        print('Catalog refresh unavailable:', type(exc).__name__, str(exc)[:200])
        if not path.exists():
            path.write_text('[]\n', encoding='utf8')
        return
    if not variants:
        print('Catalog empty; keeping previous data')
        return
    # Catalog has no personal information: model, colour, storage, Apple part number.
    variants.sort(key=lambda v: (v['model'], v['storage'], v['color']))
    serialized = json.dumps(variants, indent=2, ensure_ascii=False) + '\n'
    if not path.exists() or path.read_text(encoding='utf8') != serialized:
        path.write_text(serialized, encoding='utf8')
        print(f'Updated catalog: {len(variants)} variants')
    else:
        print(f'Catalog unchanged: {len(variants)} variants')


if __name__ == '__main__':
    main()
