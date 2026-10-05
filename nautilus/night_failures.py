#!/usr/bin/env python
"""Turn a job's status rows into a sweep manifest of the nights to retry (design 4.8.6).

Usage:
    python nautilus/night_failures.py JOB_NAME [--out nautilus/manifests/sweep_<JOB>.csv]
        [--no-pull]

Pulls ``runs/<JOB_NAME>/status/`` from the bucket (``s3_sync.py``; skip with
``--no-pull``), concatenates the per-pod rows into
``$KECK_ETCS_DATA/runs/<JOB_NAME>/status.ecsv``, and writes the nights whose
status is neither ``success`` nor ``skipped`` to a night manifest (columns
``night, instrument, s3_prefix, standard, slit, spec2d, notes``, plus the
optional columns ``std_class, jmag_2mass, std_ra, std_dec, filter`` when any status
row carries them, so a swept A0V night keeps its standard; plan S15a/S15b)
ready to be the ConfigMap of a sweep job.

A night that has failed twice for a *data* reason (``no calibs``, ``no
trace``) across all jobs under ``runs/`` is not retried. It is listed as
``data failure`` on stdout instead. Every other failure (setup, reduce, sens,
gate, push, pull, pin check) is retried.
"""
import argparse
import csv
import subprocess
import sys
from collections import Counter
from pathlib import Path

from astropy.table import Table, vstack

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[1]
DATA_REASONS = {'no calibs', 'no trace'}
COLS = ('night', 'instrument', 's3_prefix', 'standard', 'slit', 'spec2d', 'notes')
OPTIONAL_COLS = ('std_class', 'jmag_2mass', 'std_ra', 'std_dec', 'filter')   # nautilus/status_row.py


def cell(r, c):
    """A manifest cell: '' for a column the row lacks or a masked value."""
    if c not in r.colnames:
        return ''
    v = r[c]
    return '' if (hasattr(v, 'mask') and v.mask) or str(v) in ('--', 'None') else v


def read_rows(job):
    files = sorted((paths.data_root() / 'runs' / job / 'status').glob('*.ecsv'))
    return vstack([Table.read(f, format='ascii.ecsv') for f in files]) if files else None


def main(job, out=None, no_pull=False):
    sync = [sys.executable, str(REPO / 'scripts' / 'nautilus' / 's3_sync.py'), 'pull']
    if not no_pull:
        if subprocess.run(sync + [f'runs/{job}/status']).returncode != 0:
            return 1
    tbl = read_rows(job)
    if tbl is None:
        print(f'no status rows for job {job}')
        return 1
    tbl.write(paths.data_root() / 'runs' / job / 'status.ecsv', format='ascii.ecsv', overwrite=True)

    # data-reason failure counts across every job we have rows for locally
    history = Counter()
    for d in sorted((paths.data_root() / 'runs').glob('*/status')):
        t = read_rows(d.parent.name)
        for r in t if t is not None else []:
            if r['status'] in DATA_REASONS:
                history[str(r['night'])] += 1

    counts = Counter(str(s) for s in tbl['status'])
    print(f'job {job}: {len(tbl)} rows; ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    retry, dead = [], []
    for r in tbl:
        if r['status'] in ('success', 'skipped'):
            continue
        if r['status'] in DATA_REASONS and history[str(r['night'])] >= 2:
            dead.append(r)
        else:
            retry.append(r)
    for r in dead:
        print(f"  data failure (not retried): {r['night']} {r['status']}: {r['error']}")
    out = Path(out) if out else REPO / 'nautilus' / 'manifests' / f'sweep_{job}.csv'
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = COLS + tuple(c for c in OPTIONAL_COLS if any(cell(r, c) != '' for r in retry))
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in retry:
            w.writerow([cell(r, c) for c in cols])
    print(f'{len(retry)} night(s) to retry -> {out}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('job', help='Job name (runs/<job>/status on the bucket)')
    p.add_argument('--out', help='Sweep manifest CSV')
    p.add_argument('--no-pull', action='store_true', help='Use the local rows only')
    sys.exit(main(**vars(p.parse_args())))
