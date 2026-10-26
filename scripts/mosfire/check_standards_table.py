#!/usr/bin/env python
"""Check the merged standards and monitor tables against the success nights (plan S15c "Verify").

Usage:
    conda run -n pypeit14b python scripts/mosfire/check_standards_table.py [--status FILE.ecsv]

Inputs: ``keck_etcs/data/mosfire/throughput/standards.ecsv``,
``keck_etcs/data/mosfire/monitor/calib_monitor.ecsv`` and the status table of
``nautilus/status_table.py`` (default
``$KECK_ETCS_DATA/mosfire/status_table.ecsv``). Checks and reports:

- every ``success`` night has exactly one row (a row's night is its
  ``s3_prefix``), and every row comes from a ``success`` night;
- every row has the six provenance columns (``image``, ``image_digest``,
  ``pypeit_git_sha``, ``keck_etcs_git_sha``, ``job_name``, ``s3_prefix``)
  filled;
- the wide-slit rows (not ``narrow``) that can enter an era curve (not
  ``excluded``): their count, distinct standards and spread over the eras of
  ``MOSFIRE.eras``, against the milestone target (>= 10 standards over
  >= 2 eras);
- every ``success`` night has monitor rows; the ``monitor_failed`` count;
- a night in the status table that is neither ``success`` nor a row is
  listed with its recorded status.

Read-only. Exit 1 when a check fails (the milestone is reported, not
enforced).
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from astropy.table import Table

from keck_etcs import paths
from keck_etcs.calib import combine
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'standards.ecsv'
MONITOR = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'monitor' / 'calib_monitor.ecsv'
PROVENANCE = ('image', 'image_digest', 'pypeit_git_sha', 'keck_etcs_git_sha', 'job_name', 's3_prefix')


def filled(v):
    return v is not None and str(v).strip() not in ('', '--', 'None', 'unknown')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--status', default=str(paths.data_root() / 'mosfire' / 'status_table.ecsv'))
    a = ap.parse_args(argv)
    st = Table.read(a.status, format='ascii.ecsv')
    rows = Table.read(TABLE, format='ascii.ecsv')
    mon = Table.read(MONITOR, format='ascii.ecsv')
    bad = []

    success = sorted(str(r['night']) for r in st if r['status'] == 'success')
    row_nights = Counter(str(r['s3_prefix']).rstrip('/').split('/')[-1] for r in rows)
    multi = [n for n, c in row_nights.items() if c > 1]
    no_row = [n for n in success if n not in row_nights]
    stray = [n for n in row_nights if n not in success]
    print(f'success nights: {len(success)}; rows: {len(rows)} on {len(row_nights)} nights')
    for label, lst in (('success nights without a row', no_row), ('nights with several rows', multi),
                       ('rows from a night that is not success', stray)):
        if lst:
            bad.append(label)
            print(f'  FAIL {label}: {lst}')
    others = [(str(r['night']), str(r['status'])) for r in st if r['status'] != 'success']
    print(f'  other nights in the status table (recorded failures): {others or "none"}')

    unfilled = [(str(r['standard']), str(r['date']), c) for r in rows for c in PROVENANCE if not filled(r[c])]
    print(f'provenance: {len(rows) * len(PROVENANCE) - len(unfilled)}/{len(rows) * len(PROVENANCE)} cells filled')
    if unfilled:
        bad.append('provenance')
        print(f'  FAIL unfilled: {unfilled}')

    flags = [str(r['flag']) for r in rows]
    usable = [r for r, f in zip(rows, flags) if 'narrow' not in f and 'excluded' not in f]
    print(f"flags: {dict(Counter(x for f in flags for x in f.split(',')))}")
    print(f'wide-slit rows: {sum("narrow" not in f for f in flags)}; usable for era curves (not excluded): '
          f'{len(usable)}, {len({str(r["standard"]) for r in usable})} distinct standards')
    eras = []
    for era in MOSFIRE.eras:
        inn = [r for r in usable if combine.in_era(str(r['date']), era)]
        eras.append(era.name if inn else None)
        by = Counter(f"{r['standard']}/{r['filter']}" for r in inn)
        print(f'  era {era.name}: {len(inn)} rows, {len({str(r["standard"]) for r in inn})} standards {dict(by)}')
    n_std = len({str(r['standard']) for r in usable})
    n_eras = sum(e is not None for e in eras)
    print(f'milestone (>= 10 standards over >= 2 eras): {n_std} standards over {n_eras} eras -> '
          f'{"MET" if n_std >= 10 and n_eras >= 2 else "NOT MET"}')

    mon_nights = Counter(str(n) for n in mon['night'])
    no_mon = [n for n in success if mon_nights.get(n, 0) == 0]
    failed = Counter(str(n) for n, f in zip(mon['night'], mon['flag']) if 'monitor_failed' in str(f))
    print(f'monitor: {len(mon)} rows on {len(mon_nights)} nights; monitor_failed rows: {sum(failed.values())} '
          f'{dict(failed) if failed else ""}')
    if no_mon:
        bad.append('monitor rows')
        print(f'  FAIL success nights without monitor rows: {no_mon}')

    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
