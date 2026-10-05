#!/usr/bin/env python
"""Static checks on the Nautilus manifests (S4b): YAML, the bash block, consistency.

Usage:
    python nautilus/validate_manifests.py

For every ``nautilus/*.yaml``: ``yaml.safe_load`` succeeds, ``kind`` and
``metadata.namespace == pypeit``; for each container whose command is
``bash -lc``, the script block passes ``bash -n``. For the job manifests,
``night_job.yaml`` and ``validate_job.yaml`` must carry byte-identical script
blocks; every Job except the KOA probe (no bucket access) mounts the
credentials secret at ``/root/.aws/credentials`` (subPath ``credentials``)
and an ``emptyDir`` at ``/scratch``; the reduction jobs also set the env
variables of plan step S4b. Exit status 1 on any failure.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

NO_BUCKET = {'koa_probe_job.yaml'}
"""Manifests that touch no bucket (no credentials or scratch checks): the KOA reachability probe."""
REDUCTION_JOBS = {'night_job.yaml', 'validate_job.yaml'}
"""Jobs that must set the S4b environment (JOB_ENV); other Jobs (KOA downloads) only need credentials and scratch."""

HERE = Path(__file__).resolve().parent
JOB_ENV = {'BUCKET', 'ENDPOINT_URL', 'HOME', 'KECK_ETCS_IMAGE', 'KECK_ETCS_IMAGE_DIGEST',
           'OMP_NUM_THREADS', 'SPEC2D', 'REPLACE', 'KECK_ETCS_DATA', 'MANIFEST', 'JOB_NAME'}


def pod_spec(doc):
    return doc['spec']['template']['spec'] if doc['kind'] == 'Job' else doc['spec']


def main():
    bad, blocks = [], {}
    for path in sorted(HERE.glob('*.yaml')):
        doc = yaml.safe_load(path.read_text())
        ok = doc.get('metadata', {}).get('namespace') == 'pypeit'
        if not ok:
            bad.append(f'{path.name}: namespace is not pypeit')
        spec = pod_spec(doc)
        for c in spec['containers']:
            if c.get('command') == ['/bin/bash', '-lc']:
                block = c['args'][0]
                with tempfile.NamedTemporaryFile('w', suffix='.sh') as f:
                    f.write(block)
                    f.flush()
                    res = subprocess.run(['bash', '-n', f.name], capture_output=True, text=True)
                if res.returncode != 0:
                    bad.append(f'{path.name}: bash -n: {res.stderr.strip()}')
                blocks[path.name] = block
            if path.name in NO_BUCKET:
                continue
            mounts = {m['mountPath']: m for m in c.get('volumeMounts', [])}
            cred = mounts.get('/root/.aws/credentials')
            if cred is None or cred.get('subPath') != 'credentials':
                bad.append(f'{path.name}: credentials secret not mounted at /root/.aws/credentials')
            if doc['kind'] == 'Job':
                env = {e['name'] for e in c.get('env', [])}
                if path.name in REDUCTION_JOBS and JOB_ENV - env:
                    bad.append(f'{path.name}: missing env {sorted(JOB_ENV - env)}')
                vols = {v['name']: v for v in spec.get('volumes', [])}
                scratch = mounts.get('/scratch')
                if scratch is None or 'emptyDir' not in vols.get(scratch['name'], {}):
                    bad.append(f'{path.name}: no emptyDir at /scratch')
        print(f'{path.name}: {doc["kind"]} {doc["metadata"]["name"]} parsed')
    if blocks.get('night_job.yaml') != blocks.get('validate_job.yaml'):
        bad.append('night_job.yaml and validate_job.yaml script blocks differ')
    for b in bad:
        print(f'FAIL {b}')
    print('MANIFESTS OK' if not bad else f'{len(bad)} problem(s)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
