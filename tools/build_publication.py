#!/usr/bin/env python3
"""Rebuild the Q11/all-outcomes publication from frozen inputs and pinned source."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import tempfile
from urllib.request import urlopen

from code_ontology_bridge.inspection.bundle import build_bundle, load_dataset
from code_ontology_bridge.inspection.publication import publish

ROOT = Path(__file__).resolve().parents[1]


def fetch_sources(bundle, root):
    """Fetch only case-selected, commit-pinned public files and verify dataset hashes."""
    snapshot = bundle['snapshot']
    repo = snapshot['repo_url'].removesuffix('.git').replace('git@github.com:', 'https://github.com/')
    commit = snapshot['commit_sha']
    if not re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+', repo) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('publication source must be a pinned GitHub snapshot')
    for span in {s['path']: s for s in bundle['source_spans']}.values():
        path = root / span['path']
        if path.is_absolute() and not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('source path escapes cache')
        url = repo.replace('https://github.com/', 'https://raw.githubusercontent.com/') + '/' + commit + '/' + span['path']
        with urlopen(url, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if hashlib.sha256(raw).hexdigest() != span['file_sha256']:
            raise ValueError('pinned source hash mismatch: ' + span['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New publication directory')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--source-root', type=Path, help='Pinned checkout or selected source files; hashes are checked')
    source.add_argument('--fetch-source', action='store_true', help='Fetch only selected pinned public source files')
    args = parser.parse_args()
    example = ROOT / 'examples/auto-ontology'
    code_map = load_dataset(example / 'auto_ontology_code')
    options = dict(evidence=example / 'live/current', case=example / 'live/caller-chain-case.json')
    with tempfile.TemporaryDirectory(prefix='cob-source-') as temp:
        root = args.source_root or Path(temp)
        if args.fetch_source:
            fetch_sources(build_bundle(code_map, **options), root)
        bundle = build_bundle(code_map, source_root=root, **options)
        if any(s['excerpt_status'] != 'verified_file_hash' for s in bundle['source_spans']):
            raise ValueError('deployment requires verified source excerpts')
        manifest = publish(bundle, args.out)
    print(f"Published {manifest['question_count']} outcomes, {len(manifest['api_routes'])} API representations")
    print(f"Publication SHA-256: {manifest['publication_sha256']}")


if __name__ == '__main__':
    main()
