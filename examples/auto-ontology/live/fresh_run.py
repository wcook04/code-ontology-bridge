"""Freeze inputs, run all questions once, and retain terminal status for follow-up.

Usage: python fresh_run.py JOB_DIR UPSTREAM_CHECKOUT ENV_FILE
JOB_DIR must not exist. Credentials stay in the external ENV_FILE.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    job, upstream, keys = map(lambda p: Path(p).resolve(), sys.argv[1:4])
    job.mkdir(parents=True, exist_ok=False)
    inputs = job / 'inputs'
    inputs.mkdir()
    sources = {
        'evaluation.json': ROOT / 'examples/auto-ontology/auto_ontology_code/evaluation.json',
        'contracts.json': ROOT / 'eval/answer_contracts.json',
        'model.yaml': ROOT / 'examples/auto-ontology/auto_ontology_code.model.yaml',
    }
    for name, path in sources.items():
        shutil.copyfile(path, inputs / name)
    checks = [HERE / n for n in ('fresh_run.py', 'run_live.sh', 'ask_questions.py', 'evaluate_run.py',
                                'remap_catalog_ids.py', 'make_compat_duckdb.py', 'capture.py')]
    checks += list((HERE / 'sql').glob('*.sql'))
    patch = subprocess.check_output(['git', '-C', str(upstream), 'diff', '--binary'])
    (inputs / 'upstream.patch').write_bytes(patch)
    from code_ontology_bridge.inspection.bundle import database_digest
    manifest = {
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'bridge_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'upstream_commit': subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip(),
        'chat_model': 'deepseek/deepseek-v4.1-flash-1017', 'chat_endpoint': 'https://openrouter.ai/api/v1',
        'embedding_model': 'nvidia/nemotron-3-embed-1b',
        'reranking_model': 'nvidia/llama-nemotron-rerank-vl-1b-v2',
        'protocol': json.loads((inputs / 'contracts.json').read_text())['protocol'], 'calculation_only': True, 'workers': 3,
        'question_ids': list(range(1, 23)), 'attempts_per_question': 1,
        'custom_analyses_imported': 0,
        'input_sha256': {p.name: digest(p) for p in inputs.iterdir()},
        'runner_sha256': {str(p.relative_to(ROOT)): digest(p) for p in checks},
        'dataset_sha256': database_digest(ROOT / 'examples/auto-ontology/auto_ontology_code.duckdb'),
        'dataset_digest_algorithm': 'cob_typed_tables_v1',
        'source_database_sha256': digest(ROOT / 'examples/auto-ontology/auto_ontology_code.duckdb'),
    }
    write(job / 'manifest.json', manifest)
    write(job / 'status.json', {'state': 'running', 'pid': os.getpid(), 'started_at': manifest['started_at']})
    env = os.environ.copy()
    env.update({
        'AUTO_ONTOLOGY_CLONE': str(upstream), 'AO_RUN_DIR': str(job / 'run'),
        'PG_PORT': '54339', 'AO_BACKEND_PORT': '3111', 'AO_KEYLESS_PORT': '3101', 'AO_INGEST_PORT': '3102',
        'AO_CHAT_ENDPOINT': manifest['chat_endpoint'], 'AO_CHAT_KEY_VAR': 'OPENROUTER_API_KEY',
        'AO_CHAT_MODEL': manifest['chat_model'], 'AO_CALCULATION_ONLY': '1',
        'AO_QIDS': ' '.join(map(str, manifest['question_ids'])), 'KEYED_ONLY': '1',
        'AO_CONTRACTS': str(inputs / 'contracts.json'), 'AO_MODEL_FILE': str(inputs / 'model.yaml'),
        'AO_EVALUATION_FILE': str(inputs / 'evaluation.json'), 'AO_WORKERS': '3',
        'AO_SKIP_SYNC': '1', 'UV_CACHE_DIR': str(ROOT / 'build/uv-cache'),
        'PYTHONUNBUFFERED': '1',
    })
    code = 1
    try:
        with (job / 'runner.log').open('w') as output:
            code = subprocess.call(['sh', str(HERE / 'run_live.sh'), '--with-key', str(keys)],
                                   cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        from evaluate_run import evaluate
        report = evaluate(job / 'run/responses/10i_ask_with_key', inputs / 'evaluation.json', inputs / 'contracts.json')
        write(job / 'score.json', report)
        changed = [str(p.relative_to(ROOT)) for p in checks if digest(p) != manifest['runner_sha256'][str(p.relative_to(ROOT))]]
        write(job / 'status.json', {'state': 'complete' if code == 0 and not changed else 'failed',
              'exit_code': code, 'strict_rows_pass': report['strict_rows_pass'], 'pass': report['pass'],
              'questions': report['questions'], 'changed_runner_inputs': changed,
              'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    except BaseException as error:
        write(job / 'status.json', {'state': 'failed', 'exit_code': code,
                                   'error_type': type(error).__name__, 'message': str(error)})
        raise


if __name__ == '__main__':
    main()
