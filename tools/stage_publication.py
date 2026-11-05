#!/usr/bin/env python3
"""Stage verified immutable JSON assets in a Pages checkout; preserve other site files."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile

from code_ontology_bridge.inspection.bundle import encode


def stage(publication, site, source_commit):
    publication, site = Path(publication), Path(site)
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('source commit must be a full Git SHA')
    manifest_raw = (publication / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    digest = manifest['publication_sha256']
    unsigned = {k: v for k, v in manifest.items() if k != 'publication_sha256'}
    if hashlib.sha256(encode(unsigned)).hexdigest() != digest:
        raise ValueError('publication manifest digest differs')
    files = {'manifest.json': manifest_raw}
    for name, receipt in manifest['resources'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.suffix != '.json':
            raise ValueError('invalid publication resource path')
        raw = (publication / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt['sha256'] or len(raw) != receipt['bytes']:
            raise ValueError('publication resource differs: ' + name)
        files[name] = raw
    releases = site / 'data/releases'
    releases.mkdir(parents=True, exist_ok=True)
    release = releases / digest
    if release.exists():
        if any(not (release / name).is_file() or (release / name).read_bytes() != raw for name, raw in files.items()):
            raise ValueError('immutable release already exists with different bytes')
    else:
        with tempfile.TemporaryDirectory(prefix='.release-', dir=releases) as temp:
            root = Path(temp) / 'assets'
            root.mkdir()
            for name, raw in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            root.rename(release)
    pointer = {'schema_version': 'cob_deployment_v1', 'source_commit': source_commit,
               'publication_sha256': digest, 'bundle_revision': manifest['revision'],
               'manifest': f'releases/{digest}/manifest.json'}
    temporary = site / 'data/.index.json.tmp'
    temporary.write_bytes(encode(pointer) + b'\n')
    temporary.replace(site / 'data/index.json')
    (site / '.nojekyll').touch()
    return pointer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publication', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True, help='Checked-out gh-pages branch; no Git operations are performed')
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.publication, args.site, args.source_commit), indent=2))


if __name__ == '__main__':
    main()
