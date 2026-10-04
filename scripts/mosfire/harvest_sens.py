#!/usr/bin/env python
"""Harvest MOSFIRE sensfuncs into per-standard rows and curves, and merge them (design 4.4, D34).

Usage:
    # what the night pod runs (or anyone, on a synced night):
    python scripts/mosfire/harvest_sens.py harvest SENS.fits [...] --manifest run_manifest.json --out DIR
        [--standard NAME] [--filter FILE] [--raw DIR]
    python scripts/mosfire/harvest_sens.py harvest DATE --standard NAME     # night under $KECK_ETCS_DATA

    # local: fold harvest directories into the committed table
    python scripts/mosfire/harvest_sens.py --merge DIR [DIR ...]

``harvest`` writes, per sens file, ``<standard>_<date>_row.ecsv`` (one
row, design 4.4 columns) and ``<standard>_<date>.ecsv`` (the throughput
curve on the common 1 A grid with design 5.4 ``meta``) into DIR. With
``DATE``, the inputs are ``<night>/sens/sens_<NAME>_<DATE>.fits`` and
``<night>/run_manifest.json``, and DIR is ``<night>/harvest``, which the
night job pushes.

``--filter FILE`` divides out a filter curve (ECSV with ``wave_A`` and
``transmission``, part 3, S8). Without it ``thru`` is masked and
``flag = nofilter``.

``--merge`` reads every ``*_row.ecsv`` in the DIRs and appends or replaces
rows in ``keck_etcs/data/mosfire/throughput/standards.ecsv``, keyed on
``(standard, date, koa_id)``. An in-pod row (``image != local``) replaces a
local one; a local row never replaces an in-pod row; otherwise the newer
harvest wins. The matching curve files are copied into
``keck_etcs/data/mosfire/throughput/standards/``, and the table is
registered in ``keck_etcs/data/index.yaml``.
"""
import argparse
import datetime
import hashlib
import shutil
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table, vstack

from keck_etcs import paths
from keck_etcs.calib import harvest as hv

REPO = Path(__file__).resolve().parents[2]
THRU_DIR = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput'
TABLE = THRU_DIR / 'standards.ecsv'
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
CALIB_VERSION = 'mosfire-J-2026.10-dev'
KEY = ('standard', 'date', 'koa_id')


def read_filter(path):
    t = Table.read(path, format='ascii.ecsv')
    return np.asarray(t['wave_A'], float), np.asarray(t['transmission'], float)


def cmd_harvest(args):
    if len(args.inputs) == 1 and args.inputs[0].isdigit() and len(args.inputs[0]) == 8:
        date = args.inputs[0]
        if not args.standard:
            print('harvest DATE needs --standard')
            return 2
        night = paths.night_dir('mosfire', date)
        sens = [night / 'sens' / f'sens_{args.standard}_{date}.fits']
        manifest = night / 'run_manifest.json'
        outdir = Path(args.out) if args.out else night / 'harvest'
    else:
        sens = [Path(s) for s in args.inputs]
        if not args.manifest or not args.out:
            print('harvest SENS... needs --manifest and --out')
            return 2
        manifest, outdir = Path(args.manifest), Path(args.out)
    filt = read_filter(args.filter) if args.filter else None
    for s in sens:
        if not s.exists():
            print(f'missing {s}')
            return 1
        row, curve = hv.harvest(s, manifest, standard=args.standard, filter_curve=filt,
                                raw_dir=args.raw)
        rpath, cpath = hv.write_outputs(row, curve, outdir)
        print(f'{s.name}: wrote {rpath.name} and {cpath.name} in {outdir}')
        for k in hv.ROW_COLUMNS:
            print(f'  {k:24s} {row[k]}')
    return 0


def sha256sum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_pod(row):
    return str(row['image']) not in ('local', '', '--', 'None')


def cmd_merge(dirs):
    new = []
    for d in dirs:
        for rp in sorted(Path(d).glob('*_row.ecsv')):
            t = Table.read(rp, format='ascii.ecsv')
            for r in t:
                new.append((r, rp.parent / Path(str(r['thru_curve_file'])).name, t.meta.get('created', '')))
    if not new:
        print(f'no *_row.ecsv in {dirs}')
        return 1
    THRU_DIR.mkdir(parents=True, exist_ok=True)
    (THRU_DIR / 'standards').mkdir(exist_ok=True)
    table = Table.read(TABLE, format='ascii.ecsv') if TABLE.exists() else None
    rows = [] if table is None else [{c: (None if np.ma.is_masked(r[c]) else r[c])
                                      for c in table.colnames} for r in table]
    created = {} if table is None else dict(table.meta.get('row_created', {}))
    index = {tuple(str(r[k]) for k in KEY): i for i, r in enumerate(rows)}
    for r, curve_path, when in new:
        rd = {c: (None if np.ma.is_masked(r[c]) else (r[c].item() if hasattr(r[c], 'item') else r[c]))
              for c in hv.ROW_COLUMNS}
        key = tuple(str(rd[k]) for k in KEY)
        action = 'added'
        if key in index:
            old = rows[index[key]]
            if is_pod(old) and not is_pod(rd):
                print(f'  kept in-pod row {key} (local row not merged)')
                continue
            if is_pod(rd) == is_pod(old) and str(created.get('|'.join(key), '')) > str(when):
                print(f'  kept newer row {key}')
                continue
            rows[index[key]] = rd
            action = 'replaced'
        else:
            index[key] = len(rows)
            rows.append(rd)
        created['|'.join(key)] = str(when)
        shutil.copy2(curve_path, THRU_DIR / 'standards' / curve_path.name)
        print(f'  {action} {key} (image {rd["image"]}); curve {curve_path.name}')
    out = hv.row_table(rows)
    out.sort(['date', 'standard'])
    out.meta.update({
        'description': 'MOSFIRE per-standard zero points and throughput (design 4.4); '
                       'one row per standard per night; curves in standards/',
        'calib_version': CALIB_VERSION, 'row_created': created,
        'merged': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'script': 'scripts/mosfire/harvest_sens.py --merge', 'eff_aperture_m2': hv.EFF_APERTURE})
    out.write(TABLE, format='ascii.ecsv', overwrite=True)
    print(f'{len(out)} row(s) in {TABLE.relative_to(REPO)}')

    idx = yaml.safe_load(INDEX.read_text()) or {}
    idx.setdefault('files', {})['mosfire/throughput/standards.ecsv'] = {
        'calib_version': CALIB_VERSION, 'created': out.meta['merged'], 'sha256': sha256sum(TABLE),
        'script': 'scripts/mosfire/harvest_sens.py --merge',
        'provenance': f'{len(out)} per-standard rows harvested from PypeIt IR sensfuncs '
                      f'(keck_etcs.calib.harvest); curves in mosfire/throughput/standards/'}
    head = ''.join(l for l in INDEX.read_text().splitlines(keepends=True) if l.startswith('#'))
    INDEX.write_text(head + yaml.safe_dump(idx, sort_keys=False, width=100))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('command', nargs='?', choices=('harvest',))
    p.add_argument('inputs', nargs='*', help='sens files, or one night YYYYMMDD')
    p.add_argument('--manifest', help='run_manifest.json of the night')
    p.add_argument('--out', help='output directory')
    p.add_argument('--standard', help='standard name for file names (default: the sensfunc std_name)')
    p.add_argument('--filter', help='filter curve ECSV (wave_A, transmission) to divide out')
    p.add_argument('--raw', help='raw directory with manifest.ecsv (default: <manifest dir>/raw)')
    p.add_argument('--merge', nargs='+', metavar='DIR', help='merge harvest directories into standards.ecsv')
    args = p.parse_args(argv)
    if args.merge:
        return cmd_merge(args.merge)
    if args.command == 'harvest':
        return cmd_harvest(args)
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
