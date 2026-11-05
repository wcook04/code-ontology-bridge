#!/usr/bin/env python3
"""Verify a hosted publication's hashes, API revisions and evidence links."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urljoin
from urllib.request import urlopen

from code_ontology_bridge.inspection.bundle import encode


def relative_url(base, name):
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or name.startswith('/') or '..' in PurePosixPath(name).parts:
        raise ValueError('invalid publication resource path')
    return urljoin(base, name)


def verify(entry_url, expected_source_commit=None):
    def read(url):
        with urlopen(url, timeout=30) as response:
            if response.status != 200 or 'application/json' not in response.headers.get('Content-Type', ''):
                raise ValueError('expected a JSON HTTP response: ' + url)
            return response.read()

    entry = json.loads(read(entry_url))
    if expected_source_commit and entry['source_commit'] != expected_source_commit:
        raise ValueError('deployed source commit differs')
    manifest_url = relative_url(entry_url, entry['manifest'])
    manifest = json.loads(read(manifest_url))
    unsigned = {k: v for k, v in manifest.items() if k != 'publication_sha256'}
    if (hashlib.sha256(encode(unsigned)).hexdigest() != manifest['publication_sha256']
            or manifest['publication_sha256'] != entry['publication_sha256']
            or manifest['revision'] != entry['bundle_revision']):
        raise ValueError('deployment and manifest identities differ')

    def resource(item):
        name, receipt = item
        raw = read(relative_url(manifest_url, name))
        if len(raw) != receipt['bytes'] or hashlib.sha256(raw).hexdigest() != receipt['sha256']:
            raise ValueError('resource hash differs: ' + name)
        return name, json.loads(raw)

    with ThreadPoolExecutor(max_workers=6) as pool:
        resources = dict(pool.map(resource, manifest['resources'].items()))

    def route(key):
        payload = resources[manifest['api_routes'][key]]
        if payload['revision'] != manifest['revision'] or payload['schema_version'] != 'cob_inspection_api_v1':
            raise ValueError('API response identity differs: ' + key)
        return payload['data']

    for key in manifest['api_routes']:
        route(key)
    route(manifest['delivery']['entry_route'])
    outcomes = route(manifest['delivery']['outcomes_route'])
    if len(outcomes['items']) != outcomes['population_total'] or outcomes['population_total'] != manifest['question_count']:
        raise ValueError('outcome list is incomplete')
    steps = 0
    for outcome in outcomes['items']:
        question = route(outcome['question_route'])
        if question['question_id'] != outcome['question_id'] or question['assessment'] != outcome['assessment']:
            raise ValueError('outcome detail differs')
        for key in outcome['walkthrough_routes']:
            walkthrough = route(key)
            if walkthrough['question_id'] != question['question_id']:
                raise ValueError('walkthrough question differs')
            for step in walkthrough['steps']:
                if route(step['route']) != step:
                    raise ValueError('walkthrough step differs')
                steps += 1
    return {'verified_at': datetime.now(timezone.utc).isoformat(), 'entry': entry_url,
            'source_commit': entry['source_commit'], 'publication_sha256': entry['publication_sha256'],
            'resources_verified': len(resources), 'api_responses_verified': len(manifest['api_routes']),
            'outcomes_verified': len(outcomes['items']), 'walkthrough_steps_verified': steps, 'status': 'passed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entry', default='https://wcook04.github.io/code-ontology-bridge/data/index.json')
    parser.add_argument('--expected-source-commit')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    receipt = json.dumps(verify(args.entry, args.expected_source_commit), indent=2) + '\n'
    if args.receipt:
        args.receipt.write_text(receipt)
    print(receipt, end='')


if __name__ == '__main__':
    main()
