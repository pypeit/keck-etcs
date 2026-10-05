#!/usr/bin/env python
"""Turn a selection of KOA candidate nights into a Nautilus night manifest (plan S14; design 4.8.4).

Usage:
    conda run -n pypeit14b python scripts/koa/make_night_manifest.py pilot
    conda run -n pypeit14b python scripts/koa/make_night_manifest.py dryrun
    conda run -n pypeit14b python scripts/koa/make_night_manifest.py BATCH --nights 20150904 20211027 [...]
    conda run -n pypeit14b python scripts/koa/make_night_manifest.py BATCH --era 2017-02..2025-02 [--usable-wide]

Reads ``keck_etcs/data/mosfire/koa_standards_candidates.ecsv``
(``search_mosfire_standards.py``) and writes
``nautilus/manifests/nights_<BATCH>.csv``: one row per night (one pod per
night) with the columns ``night_job.yaml`` expects (design 4.8.4: ``night,
instrument, s3_prefix, standard, slit, spec2d, notes``) plus the optional
columns the driver reads (plan S15a): ``std_class`` (WD, archive or A0V),
``jmag_2mass``, ``std_ra``, ``std_dec`` (degrees) and ``filter`` (the band to
reduce; the driver's default ``--filter``). ``standard`` has its spaces
removed (it names files); ``slit`` is the mask name.

A night with several candidate rows keeps one: usable classes first (WD,
archive, A0V), then wide slits, then the most frames.

``pilot`` (plan S15a): 3-5 public wide-slit nights with flats, never
2022-04-09, picked by fixed rules so that the pilot exercises both mask
types, both standard classes and all eras:

1. a WD on a wide LONGSLIT mask with one filter that night, era
   2017-02..2025-02 (the dry-run path on another night);
2. an A0V on ``long2pos_specphot`` with matching lamp arcs (that mask is
   wavelength-calibrated on the Ne/Ar arcs), era 2017-02..2025-02, for the
   A0V/WD comparison of S15a in the same era;
3. a WD on ``long2pos_specphot`` with lamp arcs in era 2017-02..2025-02:
   white dwarfs on both masks, and a WD/A0V pair on the same mask, filter
   and era as rule 2 for the S15a comparison;
4. a usable wide-slit night in era 2012-04..2016-09 (with arcs if long2pos);
5. a usable wide-slit night in era 2025-04.. .

Within a rule the row with the most flats wins, then the most lamp arcs,
then the latest night. ``dryrun`` rewrites ``nights_dryrun.csv`` (2022-04-09,
``spec2d = 1``, the S4b note) with the optional columns.
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

REPO = Path(__file__).resolve().parents[2]
CAND = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'koa_standards_candidates.ecsv'
OUTDIR = REPO / 'nautilus' / 'manifests'
COLS = ('night', 'instrument', 's3_prefix', 'standard', 'slit', 'spec2d', 'notes')
OPTIONAL = ('std_class', 'jmag_2mass', 'std_ra', 'std_dec', 'filter')
USABLE = ('WD', 'archive', 'A0V')
CLASS_RANK = {'WD': 0, 'archive': 1, 'A0V': 2, 'other': 3}
DRYRUN_NOTE = 'S4b dry run; reference at mosfire/20220409/reference'


def best(rows):
    """The row a night keeps: usable class, wide slit, most frames."""
    return sorted(rows, key=lambda r: (CLASS_RANK.get(str(r['std_class']), 9), not bool(r['wide_slit']),
                                       -int(r['n_frames']), str(r['standard'])))[0]


def rank(rows):
    return sorted(rows, key=lambda r: (-int(r['n_flats']), -int(r['n_lamp_arcs']), -int(r['night'])))


def manifest_row(r, spec2d=0, notes=None):
    j = float(r['jmag_2mass'])
    return {'night': str(r['night']), 'instrument': 'mosfire', 's3_prefix': f"mosfire/{r['night']}",
            'standard': str(r['standard']).replace(' ', ''), 'slit': str(r['maskname']), 'spec2d': str(spec2d),
            'notes': notes if notes is not None else
            (f"{r['std_class']} {r['std_archive']} {r['std_sptype']}; {r['filter']}; {r['n_frames']} frames; "
             f"flats {r['n_flats']}; lamp arcs {r['n_lamp_arcs']}; prog {r['progid']} {r['progpi']}; era {r['era']}"),
            'std_class': str(r['std_class']), 'jmag_2mass': '' if not np.isfinite(j) else f'{j:.3f}',
            'std_ra': f"{float(r['std_ra']):.6f}", 'std_dec': f"{float(r['std_dec']):.6f}", 'filter': str(r['filter'])}


def single_filter_nights(t):
    nf = {}
    for r in t:
        nf.setdefault((str(r['night']), str(r['standard'])), set()).add(str(r['filter']))
    return {k for k, v in nf.items() if len(v) == 1}


def select_pilot(t):
    use = t[np.isin(t['std_class'], USABLE) & t['wide_slit'] & t['has_flats'] & (t['night'] != '20220409')]
    one = single_filter_nights(t)
    l2p = lambda r: 'long2pos_specphot' in str(r['maskname'])
    rules = [
        ('WD wide LONGSLIT, one filter, 2017-02..2025-02',
         lambda r: r['std_class'] == 'WD' and not l2p(r) and r['era'] == '2017-02..2025-02'
         and (str(r['night']), str(r['standard'])) in one),
        ('A0V long2pos_specphot with lamp arcs, 2017-02..2025-02',
         lambda r: r['std_class'] == 'A0V' and l2p(r) and r['lamp_arcs_match'] and r['era'] == '2017-02..2025-02'),
        ('WD long2pos_specphot with lamp arcs, 2017-02..2025-02 (same mask, filter and era as rule 2)',
         lambda r: r['std_class'] == 'WD' and l2p(r) and r['lamp_arcs_match'] and r['era'] == '2017-02..2025-02'),
        ('usable wide, 2012-04..2016-09 (arcs if long2pos)',
         lambda r: r['era'] == '2012-04..2016-09' and (not l2p(r) or r['lamp_arcs_match'])),
        ('usable wide, 2025-04..',
         lambda r: r['era'] == '2025-04..' and (str(r['night']), str(r['standard'])) in one),
    ]
    picked, why = [], []
    for name, rule in rules:
        cands = [r for r in rank(list(use)) if rule(r) and str(r['night']) not in {str(p['night']) for p in picked}]
        if cands:
            picked.append(cands[0])
            why.append(name)
    return picked, why


def write(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(COLS) + list(OPTIONAL))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def check(path):
    """Parse as night_job.yaml does (csv.DictReader, upper-cased exports); return the problems."""
    rows = list(csv.DictReader(open(path)))
    probs = [f'missing column {c}' for c in COLS if c not in rows[0]] if rows else ['no rows']
    for i, r in enumerate(rows):
        if not (r['night'].isdigit() and len(r['night']) == 8):
            probs.append(f'row {i}: night {r["night"]!r}')
        if r['s3_prefix'] != f"mosfire/{r['night']}":
            probs.append(f'row {i}: s3_prefix {r["s3_prefix"]!r}')
        if r.get('std_class') == 'A0V' and not (r.get('jmag_2mass') and r.get('std_ra') and r.get('std_dec')):
            probs.append(f'row {i}: A0V without J or coordinates')
        if ' ' in r['standard']:
            probs.append(f'row {i}: space in standard')
    if len({r['night'] for r in rows}) != len(rows):
        probs.append('duplicate nights')
    return probs, len(rows)


def main(batch, nights=None, era=None, usable_wide=False):
    t = Table.read(CAND, format='ascii.ecsv')
    why = None
    if batch == 'dryrun':
        sel = [r for r in t if str(r['night']) == '20220409' and str(r['standard']) == 'LDS749B']
        rows = [manifest_row(sel[0], spec2d=1, notes=DRYRUN_NOTE)]
    elif batch == 'pilot':
        picked, why = select_pilot(t)
        rows = [manifest_row(r) for r in picked]
    else:
        sub = t
        if nights:
            sub = sub[np.isin(sub['night'], [str(n) for n in nights])]
        if era:
            sub = sub[sub['era'] == era]
        if usable_wide:
            sub = sub[np.isin(sub['std_class'], USABLE) & sub['wide_slit'] & sub['has_flats']]
        by_night = {}
        for r in sub:
            by_night.setdefault(str(r['night']), []).append(r)
        rows = [manifest_row(best(v)) for _, v in sorted(by_night.items())]
    path = write(rows, OUTDIR / f'nights_{batch}.csv')
    probs, n = check(path)
    print(f'wrote {path.relative_to(REPO)}: {n} night(s)')
    for i, r in enumerate(rows):
        print(f"  {r['night']} {r['standard']:12s} {r['std_class']:7s} {r['slit']:26s} {r['filter']:3s} J={r['jmag_2mass'] or '-':>6s}"
              + (f'   <- {why[i]}' if why else ''))
    print('  manifest check: ' + ('OK (parses with the columns night_job.yaml expects)' if not probs else '; '.join(probs)))
    return 0 if not probs else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('batch', help='pilot, dryrun, or a batch name')
    p.add_argument('--nights', nargs='+')
    p.add_argument('--era')
    p.add_argument('--usable-wide', action='store_true', help='only usable wide-slit nights with flats')
    a = p.parse_args()
    sys.exit(main(a.batch, a.nights, a.era, a.usable_wide))
