#!/usr/bin/env python
"""Quasar-program science exposures that can serve as S/N validation points (KOA prompt 3; design 6.1, D9).

Usage:
    conda run -n pypeit14b python scripts/koa/find_validation_targets.py

From the cached KOA census (``$KECK_ETCS_DATA/koa/koa_mosfire_J_longslit_frames.xml``,
``search_mosfire_standards.py``) and the candidate table, this lists every
on-sky science exposure of the Hennawi/Yang/Wang programs (D9) on a narrow
J/J2/J3 long slit with at least 55 s, grouped per (night, target, filter,
mask), and finds the night's standard in the same filter. A target is a
**validation point** (``validation = True``) when that standard is
reducible (flats and a wavelength calibrator; ``reducible`` in the candidate
table), so the night yields both a sensfunc and the science spectra (design
6.1: flux with the same night's standard, compare ETC and measured S/N).

Writes:

- ``keck_etcs/data/mosfire/koa_validation_targets.ecsv`` (registered in
  ``index.yaml``): ``night, target, filter, maskname, slit_width_arcsec,
  n_exposures, exptime_s, total_exptime_s, sampmode, numreads, airmass,
  ra, dec, progid, progpi, koaids, standard, std_class, std_reducible,
  std_wide_slit, validation, on_s3_raw``;
- ``nautilus/manifests/nights_validation.csv``: one row per validation night
  (the standard's row, ``spec2d = 1``), for the downloads of the science
  frames and later the reductions;
- ``spec2d = 1`` for those nights in ``nights_batch1.csv`` and
  ``nights_pilot.csv``, so the reduction pods push ``spec2d_*`` for the
  validation step. 2022-04-09 keeps its dry-run row (already ``spec2d = 1``).
"""
import csv
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.coordinates import SkyCoord
from astropy.table import Table

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


def main():
    fr = Table.read(paths.data_root() / 'koa' / 'koa_mosfire_J_longslit_frames.xml', format='votable')
    fr['night'] = [census.night_of(d, u) for d, u in zip(fr['date_obs'], fr['ut'])]
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
    t.meta = {'description': 'Hennawi/Yang/Wang science exposures usable as S/N validation points (design 6.1, D9; '
                             'KOA prompt 3)', 'source': 'KOA TAP census cache (search_mosfire_standards.py)',
              'selection': 'on-sky, narrow LONGSLIT, >= 55 s, priority program, not a standard; validation = a '
                           'reducible same-night standard in the same filter',
              'created': now, 'script': SCRIPT, 'keck_etcs_version': keck_etcs.__version__}
    for c in ('exptime_s', 'total_exptime_s', 'airmass', 'ra', 'dec', 'slit_width_arcsec'):
        t[c].format = '.6g'
    t.write(OUT, format='ascii.ecsv', overwrite=True)
    census.register({str(OUT.relative_to(REPO / 'keck_etcs' / 'data')): {
        'calib_version': census.CALIB_VERSION, 'created': now, 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'script': SCRIPT, 'provenance': f'{len(t)} Hennawi/Yang/Wang science targets from the KOA census; '
                                        f'{int(np.sum(t["validation"]))} with a reducible same-night standard'}})

    val = t[t['validation']]
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

    print(f'science targets: {len(t)} (night x target x filter x mask) on {len(set(t["night"]))} nights; '
          f'validation points: {len(val)} on {len(set(val["night"]))} nights')
    for r in t:
        print(f"  {r['night']} {r['target']:16s} {r['filter']:3s} {r['maskname']:16s} {r['n_exposures']:3d} x "
              f"{r['exptime_s']:6.1f} s = {r['total_exptime_s']:7.0f} s | std {r['standard'] or '-':8s} "
              f"{'reducible' if r['std_reducible'] else 'not reducible':13s} -> {'VALIDATION' if r['validation'] else '-'}")
    print(f'wrote {path.relative_to(REPO)} ({n_rows} nights, spec2d = 1): '
          + ('OK' if not probs else '; '.join(probs)))
    print(f'spec2d set to 1 in: {changed}')
    return 0 if not probs else 1


if __name__ == '__main__':
    sys.exit(main())
