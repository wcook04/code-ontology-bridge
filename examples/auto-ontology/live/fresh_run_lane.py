"""Run fresh_run.py with every local port shifted, so two runs can share one machine.

Usage: fresh_run_lane.py [--native-nvidia] [--workers N] OFFSET JOB_DIR UPSTREAM KEYS

fresh_run.py fixes the PostgreSQL and backend ports. This wrapper adds OFFSET to each of them
before run_live.sh starts and changes nothing else: the runner files, inputs, model calls and
scoring are the ones fresh_run.py checks and records. The offset is written to lane.json in the
job directory.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fresh_run  # noqa: E402

PORTS = ('PG_PORT', 'AO_BACKEND_PORT', 'AO_KEYLESS_PORT', 'AO_INGEST_PORT')


def main():
    native = '--native-nvidia' in sys.argv
    if native:
        sys.argv.remove('--native-nvidia')
    workers = None
    if '--workers' in sys.argv:
        i = sys.argv.index('--workers')
        workers = int(sys.argv[i + 1])
        del sys.argv[i:i + 2]
    offset = int(sys.argv.pop(1))
    job = Path(sys.argv[1]).resolve()
    call = subprocess.call

    def shifted(args, **kwargs):
        env = dict(kwargs.get('env') or {})
        for name in PORTS:
            if name in env:
                env[name] = str(int(env[name]) + offset)
        lane = {'port_offset': offset, 'ports': {n: env.get(n) for n in PORTS}}
        if native:
            # Without AO_CHAT_ENDPOINT, run_live.sh sends chat to the NVIDIA endpoint with the model in
            # AO_CHAT_MODEL, and Auto Ontology picks its ChatNVIDIA client from the model name. The patch's
            # thinking switch, off unless <ROLE>_ENABLE_THINKING is set, is sent only on that client.
            env.pop('AO_CHAT_ENDPOINT', None)
            env.pop('AO_CHAT_KEY_VAR', None)
            lane['chat_route'] = 'NVIDIA endpoint through ChatNVIDIA, Nemotron reasoning off (enable_thinking: false)'
        if workers is not None:
            # The manifest is written before this call; record the concurrency actually used.
            env['AO_WORKERS'] = str(workers)
            lane['workers'] = workers
            manifest = json.loads((job / 'manifest.json').read_text())
            manifest['workers'] = workers
            (job / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        kwargs['env'] = env
        (job / 'lane.json').write_text(json.dumps(lane, indent=2) + '\n')
        return call(args, **kwargs)

    fresh_run.subprocess.call = shifted
    fresh_run.main()


if __name__ == '__main__':
    main()
