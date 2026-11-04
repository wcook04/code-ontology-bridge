"""Frontend contracts retain exact evidence and static/live parity."""
import hashlib
import json
from urllib.parse import urlsplit, parse_qsl

import pytest

from code_ontology_bridge.inspection.api import APIError, Inspector
from code_ontology_bridge.inspection.bundle import encode
from code_ontology_bridge.inspection.publication import publish
from code_ontology_bridge.inspection.http import Application
from test_inspection import request
from test_publication import bundle


def test_walkthrough_is_linked_to_exact_evidence(bundle):
    api = Inspector(bundle)
    walk = api.query('/api/v1/walkthroughs/caller-chain-q11', {})
    steps = {s['id']: s for s in walk['steps']}
    assert list(steps) == ['source', 'records', 'model', 'request', 'sql', 'answer']
    question = api.query(walk['question_route'], {})
    assert steps['request']['data']['request'] == question['request']
    assert steps['sql']['data']['sql'] == question['sql']
    assert steps['answer']['data']['result_tables'] == question['result_tables']
    assert steps['model']['data']['stages']['compiled_model']['status'] == 'not_captured'
    assert len(steps['model']['data']['terms']) == 3
    assert {t['id'] for t in steps['model']['data']['tables']} == {r for t in steps['model']['data']['terms'] for r in t['represents']}
    spans = {s['id']: s for s in steps['source']['data']['spans']}
    assert spans[steps['source']['data']['focus_span_ids'][0]]['line_start'] == 203
    for i, step in enumerate(walk['steps']):
        assert api.query(step['route'], {}) == step
        assert step['previous'] == (walk['steps'][i - 1]['id'] if i else None)
        assert step['next'] == (walk['steps'][i + 1]['id'] if i < 5 else None)
    for path in ('missing', 'caller-chain-q11/steps/missing', 'caller-chain-q11/extra'):
        assert request(Application(bundle), '/api/v1/walkthroughs/' + path)['status'] == 404


def test_all_outcomes_and_filtered_denominators(bundle):
    api = Inspector(bundle)
    all_rows = api.query('/api/v1/outcomes', {})
    assert [r['question_id'] for r in all_rows['items']] == list(range(1, 23))
    assert all_rows['population_counts'] == {'table_match': {'pass': 21, 'fail': 1},
        'prose_review': {'substantive': 20, 'unknown': 1, 'fail': 1}}
    for params, ids in [({'table_match': 'fail'}, [2]), ({'prose_review': 'fail'}, [14]),
                        ({'prose_review': 'unknown'}, [2]), ({'q': 'Q11'}, [11])]:
        page = api.query('/api/v1/outcomes', params)
        assert [r['question_id'] for r in page['items']] == ids
        assert page['population_total'] == 22 and page['total'] == len(ids)
        assert page['population_counts'] == all_rows['population_counts']
    assert api.query('/api/v1/outcomes', {'limit': '1', 'offset': '21'})['next_offset'] is None
    for params in ({'table_match': 'yes'}, {'prose_review': 'pass'}, {'q': '  '}, {'q': 'x' * 161}, {'oops': '1'}):
        with pytest.raises(APIError) as error:
            api.query('/api/v1/outcomes', params)
        assert error.value.status == 400


def test_static_routes_match_live_responses_and_every_resource_hash(bundle, tmp_path):
    out = tmp_path / 'publication'
    manifest = publish(bundle, out)
    api = Inspector(bundle)
    assert manifest['delivery']['query_parameters'] is False
    for route, filename in manifest['api_routes'].items():
        parsed = urlsplit(route)
        assert json.loads((out / filename).read_bytes()) == api.response(parsed.path, dict(parse_qsl(parsed.query)))
    for filename, receipt in manifest['resources'].items():
        raw = (out / filename).read_bytes()
        assert len(raw) == receipt['bytes']
        assert hashlib.sha256(raw).hexdigest() == receipt['sha256']
    digest = manifest.pop('publication_sha256')
    assert hashlib.sha256(encode(manifest)).hexdigest() == digest
    routes = manifest['api_routes']
    assert all(f'/api/v1/questions/{i}' in routes for i in range(1, 23))
    walk = json.loads((out / routes[manifest['delivery']['entry_route']]).read_bytes())['data']
    assert all(step['route'] in routes for step in walk['steps'])


def test_stage_preserves_frontend_and_rejects_modified_assets(bundle, tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('stage_publication', Path(__file__).resolve().parents[2] / 'tools/stage_publication.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    publication = tmp_path / 'publication'
    publish(bundle, publication)
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'index.html').write_text('existing frontend')
    pointer = module.stage(publication, site, '1' * 40)
    assert (site / 'index.html').read_text() == 'existing frontend'
    assert json.loads((site / 'data/index.json').read_text()) == pointer
    manifest = json.loads((site / 'data' / pointer['manifest']).read_text())
    assert manifest['publication_sha256'] == pointer['publication_sha256']
    assert module.stage(publication, site, '1' * 40) == pointer
    (publication / 'questions/11.json').write_text('{}')
    with pytest.raises(ValueError, match='resource differs'):
        module.stage(publication, site, '2' * 40)
    assert json.loads((site / 'data/index.json').read_text()) == pointer


def test_publication_without_authored_case_has_resolvable_entry(bundle, tmp_path):
    import copy
    detached = copy.deepcopy(bundle)
    detached['cases'] = []
    detached['source_spans'] = []
    manifest = publish(detached, tmp_path / 'no-case')
    assert manifest['delivery']['entry_route'] in manifest['api_routes']
