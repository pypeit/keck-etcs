#!/usr/bin/env python
"""Quasar-program science exposures that can serve as S/N validation points, per band (KOA prompt 3, S23c; design 6.1, 9.7, D9).

Usage:
    conda run -n pypeit14b python scripts/koa/find_validation_targets.py [--filters J Y H K]

From the cached KOA census frames
(``$KECK_ETCS_DATA/koa/koa_mosfire_<token>_longslit_frames.xml`` of every
``--filters`` token, as ``search_mosfire_standards.py`` caches them;
default: every band group whose cache exists) and the candidate table,
this lists every on-sky science exposure of the Hennawi/Yang/Wang programs
(D9) on a narrow long slit with at least 55 s, grouped per (night, target,
filter, mask), and finds the night's standard in the same filter. A target
is a **validation point** (``validation = True``) when that standard is
reducible (flats and a wavelength calibrator; ``reducible`` in the
candidate table), so the night yields both a sensfunc and the science
spectra (design 6.1: flux with the same night's standard, compare ETC and
measured S/N). The rules are the same in every band (design 9.7); the
per-band summary says whether the program's nights carry a same-night
wide-slit standard, and names the dev-suite fallbacks of 9.7 for a band
without one (J2132-1434 in Y, 2019-11-20, standard GD71 two nights earlier
through a 1" slit; Per-emb 25 in K, 2019-10-13).

Writes:

- ``keck_etcs/data/mosfire/koa_validation_targets.ecsv`` (registered in
  ``index.yaml``; all bands): ``night, target, filter, maskname,
  slit_width_arcsec, n_exposures, exptime_s, total_exptime_s, sampmode,
  numreads, airmass, ra, dec, progid, progpi, koaids, standard, std_class,
  std_reducible, std_wide_slit, validation``;
- ``nautilus/manifests/nights_validation.csv``: one row per validation night
  of the J group (:data:`MANIFEST_FILTERS`; the standard's row, ``spec2d =
  1``), for the downloads of the science frames and later the reductions.
  Nights of the other bands wait for the multi-band manifests of S23d
  (``band`` column, D55) and are only listed here;
- ``spec2d = 1`` for those nights in ``nights_batch1.csv`` and
  ``nights_pilot.csv``, so the reduction pods push ``spec2d_*`` for the
  validation step. 2022-04-09 keeps its dry-run row (already ``spec2d = 1``).
"""
import argparse
import csv
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.coordinates import SkyCoord
from astropy.table import Table, vstack

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import keck_etcs  # noqa: E402
from keck_etcs import paths  # noqa: E402
import make_night_manifest as mm  # noqa: E402
import search_mosfire_standards as census  # noqa: E402

OUT = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'koa_validation_targets.ecsv'
MANIFESTS = REPO / 'nautilus' / 'manifests'
SCRIPT = 'scripts/koa/find_validation_targets.py'
MANIFEST_FILTERS = ('J', 'J2', 'J3')
"""Filters whose validation nights go into ``nights_validation.csv`` (the J-group manifests; S23d adds ``band``)."""
FALLBACKS = {'Y': 'dev-suite Y_long: J2132-1434, 2019-11-20 (standard GD71 two nights earlier, 1" slit; weaker test)',
             'K': 'dev-suite K_long: Per-emb 25, 2019-10-13 (bright embedded source; thermal continuum, not the faint regime)'}
"""Design 9.7 fallbacks for a band without a same-night wide-slit standard on a program night."""


def set_spec2d(path, nights):
    rows = list(csv.DictReader(open(path)))
    if not rows:
        return 0
    n = 0
    for r in rows:
        if r['night'] in nights and r['spec2d'] != '1':
            r['spec2d'] = '1'
            n += 1
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return n


def load_frames(tokens=None):
    """The cached census frames of the tokens (default: every band group with a cache), stacked."""
    cache = paths.data_root() / 'koa'
    if tokens is None:
        tokens = [t for t in census.FILTER_GROUPS if census.frames_cache(cache, t).exists()]
    parts = []
    for t in tokens:
        f = census.frames_cache(cache, t)
        if not f.exists():
            raise FileNotFoundError(f'{f}: run search_mosfire_standards.py --filters {t} first')
        parts.append(Table.read(f, format='votable'))
        print(f'frames {t}: {len(parts[-1])} from {f.name}')
    fr = vstack(parts, metadata_conflicts='silent') if len(parts) > 1 else parts[0]
    fr['night'] = [census.night_of(d, u) for d, u in zip(fr['date_obs'], fr['ut'])]
    return fr, tokens


def main(tokens=None):
    fr, tokens = load_frames(tokens)
    on, _, _ = census.frame_classes(fr)
    cand = Table.read(mm.CAND, format='ascii.ecsv')
    prio = np.array([any(p in str(x).lower() for p in census.PRIORITY_PI) for x in fr['progpi']])
    narrow = np.array(['LONGSLIT' in str(m) and census.slit_of(m)[0] < census.WIDE_SLIT for m in fr['maskname']])
    sci = fr[on & prio & narrow & (np.asarray(fr['truitime'], float) >= census.MIN_OH_EXPTIME)]
    # drop frames on a standard star (e.g. Feige110 taken by the program on a narrow slit)
    cs = SkyCoord(cand['std_ra'], cand['std_dec'], unit='deg')
    _, sep, _ = SkyCoord(sci['ra'], sci['dec'], unit='deg').match_to_catalog_sky(cs)
    sci = sci[sep.arcsec > census.MATCH_ARCSEC]
    groups = {}
    for r in sci:
        groups.setdefault((str(r['night']), str(r['targname']).strip(), str(r['filter']), str(r['maskname'])), []).append(r)
    rows = []
    for (night, target, filt, mask), g in sorted(groups.items()):
        st = [r for r in cand if str(r['night']) == night and str(r['filter']) == filt
              and r['std_class'] in mm.USABLE]
        best = sorted(st, key=lambda r: (not bool(r['reducible']), not bool(r['wide_slit'])))[0] if st else None
        uniq = lambda c: ','.join(sorted({str(r[c]) for r in g}))
        rows.append({
            'night': night, 'target': target, 'filter': filt, 'maskname': mask,
            'slit_width_arcsec': census.slit_of(mask)[0], 'n_exposures': len(g),
            'exptime_s': float(np.median([float(r['truitime']) for r in g])),
            'total_exptime_s': float(np.sum([float(r['truitime']) for r in g])),
            'sampmode': uniq('sampmode'), 'numreads': uniq('numreads'),
            'airmass': float(np.mean([float(r['airmass']) for r in g])),
            'ra': float(np.median([float(r['ra']) for r in g])), 'dec': float(np.median([float(r['dec']) for r in g])),
            'progid': uniq('progid'), 'progpi': uniq('progpi'), 'koaids': ','.join(str(r['koaid']) for r in g),
            'standard': str(best['standard']) if best else '', 'std_class': str(best['std_class']) if best else '',
            'std_reducible': bool(best['reducible']) if best else False,
            'std_wide_slit': bool(best['wide_slit']) if best else False,
            'validation': bool(best is not None and best['reducible'])})
    t = Table(rows=rows)
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    t.meta = {'description': 'Hennawi/Yang/Wang science exposures usable as S/N validation points, all bands '
                             '(design 6.1, 9.7, D9; KOA prompt 3, S23c)',
              'source': 'KOA TAP census cache (search_mosfire_standards.py)', 'instrument': 'keck_mosfire',
              'filter_groups': list(tokens),
              'selection': 'on-sky, narrow LONGSLIT, >= 55 s, priority program, not a standard; validation = a '
                           'reducible same-night standard in the same filter',
              'fallbacks': dict(FALLBACKS),
              'created': now, 'script': SCRIPT, 'keck_etcs_version': keck_etcs.__version__}
    for c in ('exptime_s', 'total_exptime_s', 'airmass', 'ra', 'dec', 'slit_width_arcsec'):
        t[c].format = '.6g'
    t.write(OUT, format='ascii.ecsv', overwrite=True)
    census.register({str(OUT.relative_to(REPO / 'keck_etcs' / 'data')): {
        'calib_version': census.CALIB_VERSION, 'created': now, 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'script': SCRIPT, 'provenance': f'{len(t)} Hennawi/Yang/Wang science targets from the KOA census '
                                        f'({"/".join(tokens)}); {int(np.sum(t["validation"]))} with a reducible '
                                        f'same-night standard'}})

    # the manifest holds the J-group validation nights only (S23d brings the multi-band manifests)
    val = t[t['validation'] & np.isin(t['filter'], MANIFEST_FILTERS)]
    nights = sorted({str(n) for n in val['night']} - {'20220409'})
    vrows = []
    for n in nights:
        f = sorted({str(r['filter']) for r in val if str(r['night']) == n})[0]
        st = [r for r in cand if str(r['night']) == n and str(r['filter']) == f and bool(r['reducible'])]
        targets = ','.join(sorted({str(r['target']) for r in val if str(r['night']) == n}))
        row = mm.manifest_row(mm.best(st), spec2d=1)
        row['notes'] = f"validation: {targets}; " + row['notes']
        vrows.append(row)
    path = mm.write(vrows, MANIFESTS / 'nights_validation.csv')
    probs, n_rows = mm.check(path)
    changed = {p.name: set_spec2d(p, set(nights)) for p in (MANIFESTS / 'nights_batch1.csv', MANIFESTS / 'nights_pilot.csv')}

    allval = t[t['validation']]
    print(f'science targets: {len(t)} (night x target x filter x mask) on {len(set(t["night"]))} nights; '
          f'validation points: {len(allval)} on {len(set(allval["night"]))} nights '
          f'({len(val)} in the J-group manifest)')
    print('per band (program nights with a same-night usable standard; wide = that standard on a >= 3" slit):')
    for filt in sorted(set(str(f) for f in t['filter']), key=lambda f: (f[0], f)):
        s = t[t['filter'] == filt]
        n_std = len(set(s['night'][s['standard'] != '']))
        n_wide = len(set(s['night'][s['std_wide_slit']]))
        n_val = len(set(s['night'][s['validation']]))
        n_vw = len(set(s['night'][s['validation'] & s['std_wide_slit']]))
        line = (f'  {filt:3s}: {len(s):3d} targets on {len(set(s["night"])):3d} nights; with a standard {n_std}, '
                f'wide-slit {n_wide}; validation points {n_val} (wide-slit {n_vw})')
        if n_vw == 0 and filt[0] in FALLBACKS:
            line += f'; fallback: {FALLBACKS[filt[0]]}'
        print(line)
    for r in t:
        print(f"  {r['night']} {r['target']:16s} {r['filter']:3s} {r['maskname']:16s} {r['n_exposures']:3d} x "
              f"{r['exptime_s']:6.1f} s = {r['total_exptime_s']:7.0f} s | std {r['standard'] or '-':8s} "
              f"{'reducible' if r['std_reducible'] else 'not reducible':13s} -> {'VALIDATION' if r['validation'] else '-'}")
    print(f'wrote {path.relative_to(REPO)} ({n_rows} nights, spec2d = 1): '
          + ('OK' if not probs else '; '.join(probs)))
    print(f'spec2d set to 1 in: {changed}')
    return 0 if not probs else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--filters', nargs='+', metavar='BAND', help='band groups to read (default: every cached one)')
    a = p.parse_args()
    sys.exit(main(a.filters))
