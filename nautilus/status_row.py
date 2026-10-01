#!/usr/bin/env python
"""Write one night's status row for a Nautilus job (design 4.8.6).

Usage (inside a pod, after every outcome):
    python nautilus/status_row.py --status STATUS [--error TEXT] [--exit-code N]

Writes ``$KECK_ETCS_DATA/runs/<JOB_NAME>/status/<index>_<night>.ecsv``: one
row with the job name, completion index, the night-manifest columns
(``NIGHT``, ``INSTRUMENT``, ``S3_PREFIX``, ``STANDARD``, ``SLIT``, ``SPEC2D``,
``NOTES`` from the environment, as exported by the job script), ``status``
(one of :data:`STATUSES`), ``exit_code``, ``error``, the pod, node, image and
digest, and the UTC time. The job then pushes ``runs/<JOB_NAME>/status``.
One object per pod, so parallel pods never write the same key;
``night_failures.py`` concatenates them into the job's status table.
"""
import argparse
import datetime
import os
import sys
from pathlib import Path

from astropy.table import Table

from keck_etcs import paths

STATUSES = ('success', 'skipped', 'no calibs', 'setup failed', 'reduce failed', 'no trace',
            'sens failed', 'gate failed', 'push failed', 'pull failed', 'pin check failed')
MANIFEST_COLS = ('night', 'instrument', 's3_prefix', 'standard', 'slit', 'spec2d', 'notes')


def main(status, error='', exit_code=0):
    if status not in STATUSES:
        print(f'unknown status {status!r}; one of {STATUSES}')
        return 2
    job = os.environ.get('JOB_NAME') or 'local'
    index = os.environ.get('JOB_COMPLETION_INDEX', '0')
    row = {'job_name': job, 'index': int(index)}
    row.update({c: os.environ.get(c.upper(), '') for c in MANIFEST_COLS})
    row.update({'status': status, 'exit_code': int(exit_code), 'error': (error or '')[:500],
                'pod': os.environ.get('POD_NAME', ''), 'node': os.environ.get('NODE_NAME', ''),
                'image': os.environ.get('KECK_ETCS_IMAGE', 'local'),
                'image_digest': os.environ.get('KECK_ETCS_IMAGE_DIGEST', ''),
                'time': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')})
    out = paths.data_root() / 'runs' / job / 'status' / f"{int(index):04d}_{row['night']}.ecsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    Table(rows=[row]).write(out, format='ascii.ecsv', overwrite=True)
    print(f'status row: {row["night"]} {status} (exit {exit_code}) -> {out}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--status', required=True, choices=STATUSES)
    p.add_argument('--error', default='')
    p.add_argument('--exit-code', type=int, default=0)
    sys.exit(main(**vars(p.parse_args())))
