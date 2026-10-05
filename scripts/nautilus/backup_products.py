#!/usr/bin/env python
"""Back up the high-level products of the private bucket to Google Drive (design D39, 4.8.9; plan S15b, S16).

Usage:
    python scripts/nautilus/backup_products.py                         # dry run of the whole set (default)
    python scripts/nautilus/backup_products.py --run                   # copy, then rclone check --one-way
    python scripts/nautilus/backup_products.py --run --prefix mosfire/20220409 [mosfire/... ...]
    python scripts/nautilus/backup_products.py --run --release mosfire-J-2026.10 [--nights 20220409 ...]
    python scripts/nautilus/backup_products.py --check-only

A thin wrapper around ``rclone copy nautilus_s3:keck-etcs/ AIOcean:keck-etcs/``
and ``rclone check --one-way`` with one filter set. Included, per night under
``mosfire/<YYYYMMDD>/``:

- ``sens/**``: the sensfuncs, their QA plots and logs, and the A0V ``.sens``
  and ``*_std_model.json`` records the harvest needs to classify an A0V row.
  This is a superset of design 4.8.9's ``sens/sens_*.fits`` plus QA (the
  prompt's Context lists ``sens/**``);
- ``harvest/**`` (rows, curves, ``<night>_monitor.ecsv``);
- ``run_manifest.json``, ``run.log``, ``redux/*.pypeit``;
- ``redux/Science/spec1d_*``;
- ``raw/manifest.ecsv``;

and, at the bucket root, ``manifests/**`` and ``runs/**``. Everything else
is excluded: the raw frames, ``spec2d_*``, ``Calibrations/`` (pull
``WaveCalib*`` locally in S15c before relying on the backup) and ``QA/``.

The default is a dry run: it reports the objects and bytes in the set
(``rclone size``) and how many files a copy would transfer. ``--run`` copies,
then runs ``rclone check --one-way`` with the same filters and counts the
matches, missing files, differences and errors. ``--release TAG`` copies the
set of the contributing nights (``--nights``, default: every row of
``keck_etcs/data/mosfire/throughput/standards.ecsv`` not flagged
``excluded``) into ``AIOcean:keck-etcs/releases/TAG/``, which freezes a
calibration release's inputs (S16). Each run writes a JSON summary to
``$KECK_ETCS_DATA/runs/backup/`` (local; never committed) and prints it for
the prompt-doc log. Idempotent: rclone skips files already identical at the
destination. The rclone remotes hold the credentials; nothing secret is
printed.
"""
import argparse
import datetime
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from keck_etcs import paths  # noqa: E402

SRC = 'nautilus_s3:keck-etcs'
DST = 'AIOcean:keck-etcs'
NIGHT_PATTERNS = ('sens/**', 'harvest/**', 'run_manifest.json', 'run.log', 'redux/*.pypeit',
                  'redux/Science/spec1d_*', 'raw/manifest.ecsv')
ROOT_PATTERNS = ('manifests/**', 'runs/**')


def filter_rules(prefixes=None, nights=None, roots=True):
    """rclone filter lines for the D39 set, limited to ``prefixes`` (``mosfire/<night>``) or ``nights``."""
    if nights:
        prefixes = [paths.s3_prefix('mosfire', n) for n in nights]
    bases = [p.strip('/') for p in prefixes] if prefixes else ['mosfire/*']
    rules = [f'+ /{b}/{pat}' for b in bases for pat in NIGHT_PATTERNS]
    if roots:
        rules += [f'+ /{pat}' for pat in ROOT_PATTERNS]
    return rules + ['- **']


def rclone(args, check=True):
    r = subprocess.run(['rclone'] + args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"rclone {' '.join(args[:1])} failed (exit {r.returncode}):\n{r.stderr[-2000:]}")
    return r


def release_nights():
    from astropy.table import Table
    t = Table.read(REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    return sorted({str(r['s3_prefix']).split('/')[-1] for r in t if 'excluded' not in str(r['flag'])})


def main(run=False, prefixes=None, release=None, nights=None, check_only=False, src=SRC, dst=DST):
    if release:
        nights = nights or release_nights()
        dst = f'{dst}/releases/{release}'
    rules = filter_rules(prefixes, nights, roots=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    summary = {'time': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'mode': 'check' if check_only else ('run' if run else 'dry-run'),
               'src': src, 'dst': dst, 'release': release, 'nights': nights, 'prefixes': prefixes, 'filter': rules}
    with tempfile.NamedTemporaryFile('w', suffix='.rclone-filter', delete=False) as f:
        f.write('\n'.join(rules) + '\n')
        filt = f.name
    common = ['--filter-from', filt]
    size = json.loads(rclone(['size', src, '--json'] + common).stdout)
    summary['source'] = {'objects': size['count'], 'bytes': size['bytes']}
    if not check_only:
        if run:
            r = rclone(['copy', src, dst, '--stats-one-line', '--stats', '0', '-v'] + common)
            summary['copied'] = sum('Copied (new)' in ln or 'Copied (replaced' in ln for ln in r.stderr.splitlines())
        else:
            r = rclone(['copy', src, dst, '--dry-run', '-v'] + common)
            summary['would_copy'] = sum('Skipped copy as --dry-run is set' in ln for ln in r.stderr.splitlines())
    if run or check_only:
        with tempfile.NamedTemporaryFile('w', suffix='.combined', delete=False) as f:
            comb = f.name
        r = rclone(['check', src, dst, '--one-way', '--combined', comb] + common, check=False)
        marks = [ln[:1] for ln in Path(comb).read_text().splitlines() if ln]
        summary['check'] = {'match': marks.count('='), 'missing_on_dst': marks.count('-'),
                            'differ': marks.count('*'), 'error': marks.count('!'), 'exit': r.returncode,
                            'complete': r.returncode == 0 and marks.count('-') == marks.count('*') == marks.count('!') == 0}
    out = paths.data_root() / 'runs' / 'backup'
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"backup_{now.strftime('%Y%m%dT%H%M%SZ')}_{summary['mode']}.json"
    path.write_text(json.dumps(summary, indent=1) + '\n')
    src_s = summary['source']
    print(f"{summary['mode']}: {src} -> {dst}: {src_s['objects']} objects, {src_s['bytes'] / 1e6:.1f} MB in the set")
    if 'would_copy' in summary:
        print(f"  a copy would transfer {summary['would_copy']} file(s)")
    if 'copied' in summary:
        print(f"  copied {summary['copied']} file(s)")
    if 'check' in summary:
        c = summary['check']
        print(f"  rclone check --one-way: {c['match']} match, {c['missing_on_dst']} missing, {c['differ']} differ, "
              f"{c['error']} errors -> {'COMPLETE' if c['complete'] else 'INCOMPLETE'}")
    print(f'  summary: {path}')
    return 0 if ('check' not in summary or summary['check']['complete']) else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--run', action='store_true', help='copy for real (default: dry run)')
    p.add_argument('--prefix', nargs='+', dest='prefixes', help='limit to these night prefixes, e.g. mosfire/20220409')
    p.add_argument('--release', help='copy the contributing nights into releases/TAG/ (S16)')
    p.add_argument('--nights', nargs='+', help='nights (YYYYMMDD) for --release (default: from standards.ecsv)')
    p.add_argument('--check-only', action='store_true', help='only rclone check --one-way')
    p.add_argument('--src', default=SRC)
    p.add_argument('--dst', default=DST)
    a = p.parse_args()
    if a.release and not a.run and not a.check_only:
        print('note: --release without --run is a dry run')
    sys.exit(main(a.run, a.prefixes, a.release, a.nights, a.check_only, a.src, a.dst))
