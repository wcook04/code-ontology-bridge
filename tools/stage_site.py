#!/usr/bin/env python3
"""Copy the built website into a gh-pages checkout without touching its data/ tree."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

KEEP = {'data', '.git', '.nojekyll'}


def stage(dist: Path, site: Path) -> list[str]:
    if not (dist / 'index.html').is_file():
        raise SystemExit(f'{dist} has no index.html; run npm run build in site/ first')
    if (dist / 'data').exists():
        raise SystemExit(f'{dist} contains data/; the website build must not carry publication data')
    if not (site / 'data' / 'index.json').is_file():
        raise SystemExit(f'{site} has no data/index.json; stage the publication first')
    removed = []
    for entry in site.iterdir():
        if entry.name in KEEP:
            continue
        removed.append(entry.name)
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    for entry in dist.iterdir():
        target = site / entry.name
        shutil.copytree(entry, target) if entry.is_dir() else shutil.copy2(entry, target)
    (site / '.nojekyll').touch()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path('site/dist'))
    parser.add_argument('--site', type=Path, required=True, help='gh-pages checkout')
    args = parser.parse_args()
    removed = stage(args.dist.resolve(), args.site.resolve())
    print(f'staged {args.dist} into {args.site}; replaced earlier site files: {sorted(removed) or "none"}; data/ kept')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
