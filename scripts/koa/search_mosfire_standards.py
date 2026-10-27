#!/usr/bin/env python
"""KOA census of MOSFIRE long-slit standards per band, and the SAMPMODE census (plan S14, S23c; design 4.1, D13, D44, D50).

Usage:
    conda run -n pypeit14b python scripts/koa/search_mosfire_standards.py [--filters J Y H K] [--refresh]

``--filters`` names band groups (``Y``, ``J`` = J, J2 and J3, ``H``, ``K``;
:data:`FILTER_GROUPS`) or single KOA filter names. The default, ``J``,
reproduces the S14 census; the committed table is built with ``--filters
J Y H K`` (S23c). Every band is treated by the same rules; the per-band
reductions differ only through the ``filter`` column (design D50; one
table per instrument, H-1).

Queries, all over plain HTTP TAP (no ``pykoa``/``astroquery``/``pyvo``
needed); raw answers are cached under ``$KECK_ETCS_DATA/koa/`` (local, never
committed) and reused unless ``--refresh``:

1. **KOA** (``koa_mosfire``), one query per ``--filters`` token: every frame
   with ``gratmode = 'spectroscopy'``, ``filter`` in the token's filters and
   ``maskname LIKE 'LONGSLIT%'`` or ``'long2pos%'`` (:func:`base_where`;
   cache ``koa_mosfire_<token>_longslit_frames.xml``). KOA's TAP returns
   **public frames only**: anonymous queries are rewritten with
   ``current_date > add_months(date_obs, propint)``, so every candidate is
   public.
2. **The SAMPMODE census**: the ``SAMPMODE`` x ``NUMREADS`` histogram of
   every public on-sky MOSFIRE spectroscopy frame (all masks and filters),
   to answer the UTR question (D13).
3. **SIMBAD**: every star with a spectral type starting ``A0`` and V < 11
   (one all-sky query, matched locally).
4. **VizieR II/246** (2MASS PSC): J, H and Ks with their errors for each
   A0V standard found (one cone of 5" per star; ``jmag_2mass``,
   ``hmag_2mass``, ``kmag_2mass``: the A0V model of a band is scaled to
   the band's own 2MASS magnitude, D51).

Frame classes. KOA's ``koaimtyp`` is unreliable for MOSFIRE: on 2022-04-09
the J0841 and LDS749 frames and the lamp-off dome flats are all
``flatlamp``, because ``FLATSPEC = 1`` throughout (the problem
``reduce_standard.py`` works around). KOA also carries no ``FLAMP1``/``FLAMP2``,
so lamp-on and lamp-off flats cannot be told apart from KOA metadata. Classes
here:

- *on sky*: ``axestat`` tracking or slewing, target name without "FLAT";
- *dome flat*: not on sky, and a "FLAT" target or ``koaimtyp`` ``flatlamp``
  / ``flatlampoff``;
- *lamp arc*: ``pwstata7 = 1`` or ``pwstata8 = 1`` (Ne, Ar; named in
  ``pwloca7``/``pwloca8``).

``has_flats`` therefore means dome flats in the same filter on a long-slit
(or, for long2pos standards, a long2pos) mask that night; the lamp state is
checked from the headers by ``reduce_standard.py`` (``no calibs`` without
lamp-on flats).

Wavelength calibrator (``wavecal``, KOA prompt 2): a wide-slit standard's own
OH lines are too broad, so a LONGSLIT standard needs narrow-slit (< 3")
on-sky frames of the same night and filter, of at least 55 s, for the OH
lines (``oh``, ``n_oh_frames``; short telluric exposures show too little OH), as the J0841 frames served LDS749B on 2022-04-09; a
``long2pos_specphot`` standard is calibrated by PypeIt on Ne/Ar arcs taken
with a long2pos mask (``lamp``, ``n_l2p_arcs``), since standard exposures
are too short for the OH lines. ``reducible`` = usable class, flats and a
calibrator.

Standards (design 4.1). An on-sky pointing within 60" of a star in one of
PypeIt's archives (``xshooter``, ``calspec``, ``esofil``, ``noao``, ``ing``,
``lbtmods``, ``blackbody``) is that standard: class ``WD`` if its type starts
with D (or it is a blackbody DC white dwarf), else ``archive`` (CALSPEC A0V
stars such as HD116405, subdwarfs such as BD+17 4708, P330E: PypeIt fluxes
them with their measured spectra, so they are usable like the white
dwarfs). Otherwise, within 60" of a SIMBAD A0 dwarf (class V, IV/V or
unclassified; giants excluded) it is ``A0V``, with 2MASS J. A target named
HIP/HD that matches neither is ``other`` (``std_archive = none``: typically
A1V or later telluric stars, which the N3 model does not cover). The
classes extend the KOA doc's three (WD, A0V, other) with ``archive``; the
reduction driver treats WD and archive alike. Usable = WD, archive or A0V.
60" is deliberately tighter than PypeIt's 20' match tolerance, which would
also catch science fields near a standard; matches are bimodal, 0-20" (the
long slit) and 45-56" (the off-centre long2pos slits), with almost nothing
between 56" and 180".

Night: the UT date of (UT + 6 h), i.e. 08:00 to 08:00 HST, which keeps
afternoon flats and morning calibrations with their night and matches KOA's
file-name date for the night itself.

Outputs (committed, registered in ``keck_etcs/data/index.yaml``):

- ``keck_etcs/data/mosfire/koa_standards_candidates.ecsv``: one row per
  (night, standard, mask, filter), all bands in one table, with the fields
  of design 4.1 plus ``std_class``, ``slit_width_arcsec``, ``wide_slit``
  (>= 3"), ``era``, ``public``, ``has_flats``, ``n_lamp_arcs``,
  ``lamp_arcs_match`` and ``priority`` (the Hennawi/Yang/Wang program,
  D9). Column names and ``meta`` keys are instrument-neutral (the
  instrument is a ``meta`` key and the band a column), so that the other
  Keck instruments can ship the same layout under
  ``keck_etcs/data/<instrument>/``;
- ``keck_etcs/data/mosfire/koa_sampmode_census.ecsv``.

Prints, per band: candidate nights, usable wide-slit nights, the WD /
archive / A0V counts, the era coverage and the nights that hold both a
white dwarf and an A0V star (design D52's cross-tie); then the counts per
era and slit class, the SAMPMODE percentages, the fraction of candidate
nights with matching lamp arcs, the check that the 2022-04-09 LDS749B
frames are found with ``wide_slit = True`` (when J2 is queried), and the
design 9.2 TAP counts recomputed from the cached frames
(:func:`design_counts`).
"""
import argparse
import datetime
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import yaml
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.table import Table

import keck_etcs
from keck_etcs import paths
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / 'keck_etcs' / 'data'
OUT_CAND = DATA / 'mosfire' / 'koa_standards_candidates.ecsv'
OUT_SAMP = DATA / 'mosfire' / 'koa_sampmode_census.ecsv'
INDEX = DATA / 'index.yaml'
CALIB_VERSION = 'mosfire-2026.10-dev'
SCRIPT = 'scripts/koa/search_mosfire_standards.py'

KOA_TAP = 'https://koa.ipac.caltech.edu/TAP/sync'
SIMBAD_TAP = 'https://simbad.cds.unistra.fr/simbad/sim-tap/sync'
VIZIER_TAP = 'https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync'
FILTER_GROUPS = {'Y': ('Y',), 'J': ('J', 'J2', 'J3'), 'H': ('H',), 'K': ('K',)}
"""``--filters`` token -> KOA filter names (the band groups of design D49; J3 is queried with the J group
as in S14 although the ETC does not model it, D48)."""


def expand_filters(tokens):
    """``--filters`` tokens -> ``[(token, (filter, ...)), ...]`` (a group of :data:`FILTER_GROUPS` or one filter)."""
    return [(t, FILTER_GROUPS.get(t, (t,))) for t in tokens]


def base_where(filters):
    """The KOA ``WHERE`` clause of the long-slit spectroscopy frames in ``filters``."""
    names = ', '.join(f"'{f}'" for f in filters)
    return (f"gratmode = 'spectroscopy' AND filter IN ({names}) "
            "AND (maskname LIKE 'LONGSLIT%' OR maskname LIKE 'long2pos%')")


BASE_WHERE = base_where(FILTER_GROUPS['J'])
"""The S14 (J-only) clause."""
STAR_PREFIXES = ('HIP', 'HD', 'GD', 'Feige', 'G191', 'LDS', 'BD+')
"""Target-name prefixes of the design 9.2 TAP count (``scripts/mosfire/survey_other_bands.py --koa``)."""
DESIGN_COUNTS = {'Y': (11317, 230, 13), 'J': (12052, 332, 50), 'J2': (714, 14, 2), 'H': (15409, 415, 92), 'K': (27575, 372, 72)}
"""Design 9.2 (survey of 2026-10-2x): per filter, (long-slit + long2pos frames, nights with star-like
target names, long2pos_specphot nights with star-like names)."""
COLUMNS = ('koaid', 'date_obs', 'ut', 'mjd_obs', 'targname', 'object', 'ra', 'dec', 'maskname', 'filter',
           'gratmode', 'obsmode', 'sampmode', 'numreads', 'truitime', 'airmass', 'pattern', 'frameid',
           'yoffset', 'progid', 'progpi', 'koaimtyp', 'propint', 'semid', 'axestat', 'domestat', 'flatspec',
           'pwstata7', 'pwstata8', 'pwloca7', 'pwloca8')
ARCHIVES = ('xshooter', 'calspec', 'esofil', 'noao', 'ing', 'lbtmods', 'blackbody')
MATCH_ARCSEC = 60.0
WIDE_SLIT = 3.0
PRIORITY_PI = ('hennawi', 'yang', 'wang')
USABLE = ('WD', 'archive', 'A0V')
MIN_OH_EXPTIME = 55.0
"""Shortest exposure [s] whose OH lines calibrate a night (the 2022-04-09 frames are 150 s; many telluric
frames are 1.5-30 s and too faint in OH; 59.6 s frames are common)."""
NAME_HINT = re.compile(r'^\s*(HIP|HD)\s*[-_]?\s*\d+', re.I)


def tap(url, adql, cache, refresh=False, fmt='csv'):
    """Run a synchronous TAP query (cached); return an astropy Table.

    KOA's CSV does not escape quotes inside text fields (e.g. ``object =
    dome flat: longslit, 120" x 0.7"``), so KOA queries use VOTable.
    """
    import requests
    cache = Path(cache)
    if refresh or not cache.exists():
        r = requests.post(url, data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': fmt, 'QUERY': adql}, timeout=900)
        r.raise_for_status()
        if (fmt == 'csv' and r.text.lstrip().startswith('<')) or 'Failed to execute' in r.text[:2000] \
                or ('QUERY_STATUS' in r.text[:3000] and 'value="ERROR"' in r.text[:3000]):
            raise RuntimeError(f'TAP error from {url}:\n{r.text[:1500]}')
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(r.text)
    return Table.read(str(cache), format='votable') if fmt == 'votable' else Table.read(str(cache), format='ascii.csv')


def archive_stars():
    """PypeIt's archive standards: name, archive, type, magnitude, coordinates."""
    from pypeit import dataPaths
    rows = []
    for arc in ARCHIVES:
        f = (dataPaths.standards / arc).get_file_path(f'{arc}_info.txt')
        t = Table.read(f, comment='#', format='ascii')
        typ = next((c for c in ('Sp.T.', 'TYPE', 'type', 'SpT') if c in t.colnames), None)
        mag = next((c for c in ('V', 'V_MAG', 'g_MAG') if c in t.colnames), None)
        for r in t:
            raw = str(r[mag]) if mag else ''
            num = re.search(r'-?\d+(?:\.\d+)?', raw)
            rows.append({'name': str(r['Name']), 'archive': arc, 'type': str(r[typ]) if typ else '',
                         'mag': float(num.group(0)) if num else np.nan,
                         'mag_note': raw if (num and not re.fullmatch(r'\s*-?\d+(?:\.\d+)?\s*', raw)) else '',
                         'ra_s': str(r['RA_2000']), 'dec_s': str(r['DEC_2000'])})
    t = Table(rows=rows)
    c = SkyCoord(t['ra_s'], t['dec_s'], unit=(u.hourangle, u.deg))
    t['ra'], t['dec'] = c.ra.deg, c.dec.deg
    return t


def is_dwarf_a0(sp):
    sp = str(sp).strip()
    if not sp.startswith('A0'):
        return False
    lum = sp[2:].lstrip('/0123456789.+-:')
    return not re.search(r'(^|[^V])I{1,3}(?![IV])', lum) or lum.startswith('IV/V') or 'IV-V' in lum


def night_of(date_obs, ut):
    d = str(date_obs)[:10]
    h, m, s = (float(x) for x in str(ut).split(':'))
    t = datetime.datetime.fromisoformat(d) + datetime.timedelta(hours=h + 6, minutes=m, seconds=s)
    return t.strftime('%Y%m%d')


def slit_of(mask):
    m = str(mask)
    if 'long2pos_specphot' in m:
        return np.nan, True
    if 'long2pos' in m:
        return 0.7, False
    w = re.search(r'x(\d+(?:\.\d+)?)', m)
    width = float(w.group(1)) if w else np.nan
    return width, bool(np.isfinite(width) and width >= WIDE_SLIT)


def slit_length_bars(mask):
    """Number of CSU bars of a LONGSLIT mask (LONGSLIT-<bars>x<width>); -1 for long2pos masks."""
    w = re.search(r'LONGSLIT-(\d+)x', str(mask))
    return int(w.group(1)) if w else -1


TMASS_BANDS = ('j', 'h', 'k')


def tmass_mags(stars, cache_dir, refresh=False, pause=0.2):
    """2MASS J, H, Ks and errors for (name, ra, dec) from VizieR II/246, one 5" cone per star (cached as JSON).

    The S14 cache ``tmass_j.json`` held J only; since S23c the cache is
    ``tmass_jhk.json`` with ``jmag, e_jmag, hmag, e_hmag, kmag, e_kmag``
    (``k`` is Ks; a missing or blank magnitude is None).
    """
    import requests
    cache = Path(cache_dir) / 'tmass_jhk.json'
    known = json.loads(cache.read_text()) if cache.exists() and not refresh else {}
    num = lambda v: float(v) if str(v).strip() not in ('', '--', 'nan') else None
    for name, ra, dec in stars:
        if name in known:
            continue
        adql = ('SELECT "2MASS", RAJ2000, DEJ2000, Jmag, e_Jmag, Hmag, e_Hmag, Kmag, e_Kmag FROM "II/246/out" WHERE '
                f"1=CONTAINS(POINT('ICRS', RAJ2000, DEJ2000), CIRCLE('ICRS', {ra:.6f}, {dec:.6f}, {5 / 3600:.6f}))")
        r = requests.post(VIZIER_TAP, data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'QUERY': adql},
                          timeout=120)
        r.raise_for_status()
        t = Table.read(r.text, format='ascii.csv') if r.text.count('\n') > 1 else None
        if t is None or len(t) == 0:
            known[name] = None
        else:
            sep = SkyCoord(t['RAJ2000'], t['DEJ2000'], unit='deg').separation(SkyCoord(ra, dec, unit='deg')).arcsec
            k = int(np.argmin(sep))
            known[name] = {'id': str(t['2MASS'][k]).strip(), 'sep_arcsec': float(sep[k]),
                           **{f'{b}mag': num(t[f'{b.upper()}mag'][k]) for b in TMASS_BANDS},
                           **{f'e_{b}mag': num(t[f'e_{b.upper()}mag'][k]) for b in TMASS_BANDS}}
        cache.write_text(json.dumps(known, indent=1))
        time.sleep(pause)
    return known


def frame_classes(t):
    """on_sky, dome_flat, lamp_arc boolean arrays (see the module docstring)."""
    targ = np.array([str(x).upper() for x in t['targname']])
    axe = np.array([str(x).strip().lower() for x in t['axestat']])
    typ = np.array([str(x).strip().lower() for x in t['koaimtyp']])
    flatname = np.array(['FLAT' in x for x in targ])
    on_sky = np.isin(axe, ('tracking', 'slewing')) & ~flatname
    arc = (np.array([str(x) == '1' for x in t['pwstata7']]) | np.array([str(x) == '1' for x in t['pwstata8']]))
    dome = ~on_sky & ~arc & (flatname | np.isin(typ, ('flatlamp', 'flatlampoff')))
    return on_sky, dome, arc


def era_name(date_iso):
    era, warnings = MOSFIRE.era_for_date(date_iso)
    return era.name, warnings


def register(entries):
    index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {}).update(entries)
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def frames_cache(cache, token):
    """Cache file of a ``--filters`` token's KOA frames (the J group keeps its S14 name)."""
    return Path(cache) / f'koa_mosfire_{token}_longslit_frames.xml'


def load_frames(cache, tokens, refresh=False):
    """KOA long-slit spectroscopy frames of the tokens, one query each; returns ``(table, {token: adql}, {token: n})``."""
    from astropy.table import vstack
    parts, queries, counts = [], {}, {}
    for token, filters in expand_filters(tokens):
        adql = f"SELECT {', '.join(COLUMNS)} FROM koa_mosfire WHERE {base_where(filters)}"
        t = tap(KOA_TAP, adql, frames_cache(cache, token), refresh, fmt='votable')
        print(f'KOA {token} ({"/".join(filters)}): {len(t)} public MOSFIRE LONGSLIT/long2pos spectroscopy frames')
        queries[token], counts[token] = adql, len(t)
        parts.append(t)
    fr = vstack(parts, metadata_conflicts='silent') if len(parts) > 1 else parts[0]
    fr['night'] = [night_of(d, ut) for d, ut in zip(fr['date_obs'], fr['ut'])]
    return fr, queries, counts


def main(refresh=False, tokens=('J',)):
    cache = paths.data_root() / 'koa'
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    filters = [f for _, fs in expand_filters(tokens) for f in fs]

    # 1. KOA frames, per band group
    fr, queries, counts = load_frames(cache, tokens, refresh)
    on_sky, dome, arc = frame_classes(fr)
    print(f'  on sky {on_sky.sum()}, dome flats {dome.sum()}, lamp arcs {arc.sum()}, other {len(fr) - on_sky.sum() - dome.sum() - arc.sum()}')

    # 2. SAMPMODE census (all public on-sky spectroscopy)
    adql2 = ("SELECT sampmode, numreads, COUNT(*) AS n_frames FROM koa_mosfire WHERE gratmode = 'spectroscopy' "
             "AND axestat IN ('tracking', 'slewing') AND targname NOT LIKE '%FLAT%' GROUP BY sampmode, numreads")
    sm = tap(KOA_TAP, adql2, cache / 'koa_mosfire_sampmode_census.xml', refresh, fmt='votable')
    sm.sort(['sampmode', 'numreads'])
    total = int(np.sum(sm['n_frames']))
    sm['fraction'] = np.round(np.asarray(sm['n_frames'], float) / total, 5)
    names = {1: 'Single', 2: 'CDS', 3: 'MCDS', 4: 'UTR'}
    sm['mode'] = [names.get(int(s), str(s)) for s in sm['sampmode']]
    sm = sm[['mode', 'sampmode', 'numreads', 'n_frames', 'fraction']]

    # 3. standards
    arch = archive_stars()
    simbad = tap(SIMBAD_TAP, "SELECT b.main_id, b.ra, b.dec, b.sp_type, f.flux AS vmag FROM basic AS b JOIN flux AS f "
                 "ON b.oid = f.oidref WHERE f.filter = 'V' AND f.flux < 11 AND b.sp_type LIKE 'A0%'",
                 cache / 'simbad_A0_V11.csv', refresh)
    a0 = simbad[[is_dwarf_a0(s) for s in simbad['sp_type']]]
    print(f'archive standards {len(arch)}; SIMBAD A0 stars V<11 {len(simbad)}, of which dwarfs/unclassified {len(a0)}')
    c_arch = SkyCoord(arch['ra'], arch['dec'], unit='deg')
    c_a0 = SkyCoord(a0['ra'], a0['dec'], unit='deg')

    sky = fr[on_sky]
    c_sky = SkyCoord(sky['ra'], sky['dec'], unit='deg')
    ia, sa, _ = c_sky.match_to_catalog_sky(c_arch)
    i0, s0, _ = c_sky.match_to_catalog_sky(c_a0)
    std_rows = []
    for k, r in enumerate(sky):
        if sa[k].arcsec <= MATCH_ARCSEC:
            s = arch[ia[k]]
            wd = s['archive'] == 'blackbody' or str(s['type']).upper().startswith(('D', 'WD'))
            std_rows.append((k, {'standard': s['name'], 'std_class': 'WD' if wd else 'archive', 'std_archive': s['archive'],
                                 'std_sptype': s['type'], 'std_vmag': s['mag'], 'std_ra': float(s['ra']),
                                 'std_dec': float(s['dec']), 'match_sep_arcsec': float(sa[k].arcsec)}))
        elif s0[k].arcsec <= MATCH_ARCSEC:
            s = a0[i0[k]]
            std_rows.append((k, {'standard': ' '.join(str(s['main_id']).split()), 'std_class': 'A0V',
                                 'std_archive': 'simbad', 'std_sptype': str(s['sp_type']), 'std_vmag': float(s['vmag']),
                                 'std_ra': float(s['ra']), 'std_dec': float(s['dec']),
                                 'match_sep_arcsec': float(s0[k].arcsec)}))
        elif NAME_HINT.match(str(r['targname'])):
            std_rows.append((k, {'standard': ' '.join(str(r['targname']).split()), 'std_class': 'other',
                                 'std_archive': 'none', 'std_sptype': '', 'std_vmag': np.nan,
                                 'std_ra': float(r['ra']), 'std_dec': float(r['dec']), 'match_sep_arcsec': np.nan}))

    # 2MASS J, H, Ks for the A0V stars
    a0v = {(v['standard'], v['std_ra'], v['std_dec']) for _, v in std_rows if v['std_class'] == 'A0V'}
    jm = tmass_mags(sorted(a0v), cache, refresh)

    # 4. group into candidates: (night, standard, mask, filter)
    groups = {}
    for k, v in std_rows:
        r = sky[k]
        key = (r['night'], v['standard'], str(r['maskname']), str(r['filter']))
        groups.setdefault(key, {'std': v, 'rows': []})['rows'].append(r)
    # calibrations per night
    cal = {}
    for r, d, a in zip(fr, dome, arc):
        if d or a:
            cal.setdefault(str(r['night']), []).append((r, 'flat' if d else 'arc'))
    onsky_by_night = {}
    for r in sky:
        onsky_by_night.setdefault(str(r['night']), []).append(r)
    out = []
    for (night, std, mask, filt), g in sorted(groups.items()):
        rows, v = g['rows'], g['std']
        width, wide = slit_of(mask)
        l2p = 'long2pos' in mask
        same_kind = lambda m: ('long2pos' in str(m)) == l2p
        flats = [c for c, kind in cal.get(night, []) if kind == 'flat' and str(c['filter']) == filt
                 and same_kind(c['maskname'])]
        arcs_f = [c for c, kind in cal.get(night, []) if kind == 'arc' and str(c['filter']) == filt]
        arcs_l2p = [c for c in arcs_f if 'long2pos' in str(c['maskname'])]
        # OH arcs for a LONGSLIT standard: narrow-slit on-sky frames of the night, same filter, not the standard
        oh = [] if l2p else [x for x in onsky_by_night.get(night, []) if str(x['filter']) == filt
                             and float(x['truitime']) >= MIN_OH_EXPTIME
                             and 'LONGSLIT' in str(x['maskname']) and slit_of(x['maskname'])[0] < WIDE_SLIT
                             and SkyCoord(float(x['ra']), float(x['dec']), unit='deg').separation(
                                 SkyCoord(v['std_ra'], v['std_dec'], unit='deg')).arcsec > MATCH_ARCSEC]
        wavecal = ('lamp' if arcs_l2p else 'none') if 'long2pos_specphot' in mask else \
                  (('lamp' if arcs_l2p else 'none') if l2p else ('oh' if oh else 'none'))
        arcs_m = [c for c in arcs_f if str(c['maskname']) == mask or ('long2pos_specphot' in mask
                                                                      and 'long2pos' in str(c['maskname']))]
        date_iso = f'{night[:4]}-{night[4:6]}-{night[6:]}'
        era, ew = era_name(date_iso)
        uniq = lambda col: sorted({str(x) for x in (r[col] for r in rows)})
        pis = ' '.join(uniq('progpi')).lower()
        j = jm.get(v['standard']) if v['std_class'] == 'A0V' else None
        mag = lambda key: (j[key] if j and j.get(key) is not None else np.nan)
        out.append({
            'night': night, 'date': date_iso, 'era': era, 'era_note': '; '.join(ew),
            'standard': v['standard'], 'std_class': v['std_class'], 'std_archive': v['std_archive'],
            'std_sptype': v['std_sptype'], 'std_vmag': v['std_vmag'], 'std_ra': v['std_ra'], 'std_dec': v['std_dec'],
            'match_sep_arcsec': v['match_sep_arcsec'],
            'jmag_2mass': mag('jmag'), 'e_jmag_2mass': mag('e_jmag'),
            'hmag_2mass': mag('hmag'), 'e_hmag_2mass': mag('e_hmag'),
            'kmag_2mass': mag('kmag'), 'e_kmag_2mass': mag('e_kmag'),
            'tmass_id': j['id'] if j else '',
            'targname': ','.join(uniq('targname')), 'koaids': ','.join(str(r['koaid']) for r in rows),
            'n_frames': len(rows), 'maskname': mask, 'slit_width_arcsec': width,
            'slit_length_bars': slit_length_bars(mask), 'wide_slit': wide, 'filter': filt,
            'sampmode': ','.join(uniq('sampmode')), 'numreads': ','.join(uniq('numreads')),
            'truitime_s': float(np.median([float(r['truitime']) for r in rows])),
            'airmass': float(np.mean([float(r['airmass']) for r in rows])),
            'pattern': ','.join(uniq('pattern')), 'yoffsets': ','.join(uniq('yoffset')),
            'progid': ','.join(uniq('progid')), 'progpi': ','.join(uniq('progpi')),
            'public': True, 'has_flats': len(flats) > 0, 'n_flats': len(flats),
            'n_flats_koa_lampoff': sum(str(c['koaimtyp']) == 'flatlampoff' for c in flats),
            'n_lamp_arcs': len(arcs_m), 'n_lamp_arcs_filter': len(arcs_f), 'lamp_arcs_match': len(arcs_m) > 0,
            'n_oh_frames': len(oh), 'n_l2p_arcs': len(arcs_l2p), 'wavecal': wavecal,
            'reducible': bool(v['std_class'] in USABLE and len(flats) > 0 and wavecal != 'none'),
            'priority': any(p in pis for p in PRIORITY_PI),
        })
    cand = Table(rows=out)
    meta = {'description': f'KOA census of public MOSFIRE long-slit and long2pos standard-star observations in '
                           f'{", ".join(filters)} (design 4.1, D50; plan S14, S23c); one table per instrument, '
                           'all bands, the band in the filter column',
            'instrument': 'keck_mosfire', 'filters': filters, 'filter_groups': {t: list(f) for t, f in expand_filters(tokens)},
            'koa_queries': dict(queries), 'koa_rows': dict(counts), 'koa_rows_total': len(fr),
            'public_only': 'KOA TAP returns public frames only',
            'archives': list(ARCHIVES), 'match_arcsec': MATCH_ARCSEC, 'wide_slit_arcsec': WIDE_SLIT,
            'a0v_source': 'SIMBAD sp_type A0* V<11, dwarfs/unclassified', 'tmass': 'VizieR II/246, 5" cone, J/H/Ks',
            'night_definition': 'UT date of (UT + 6 h)', 'calib_version': CALIB_VERSION,
            'keck_etcs_version': keck_etcs.__version__, 'created': now, 'script': SCRIPT,
            'command': f'{SCRIPT} --filters {" ".join(tokens)}'}
    cand.meta = dict(meta)
    for c in ('std_vmag', 'std_ra', 'std_dec', 'match_sep_arcsec', 'jmag_2mass', 'e_jmag_2mass', 'hmag_2mass',
              'e_hmag_2mass', 'kmag_2mass', 'e_kmag_2mass', 'truitime_s', 'airmass'):
        cand[c].format = '.6g'
    cand.write(OUT_CAND, format='ascii.ecsv', overwrite=True)
    sm.meta = {'description': 'SAMPMODE x NUMREADS histogram of all public on-sky MOSFIRE spectroscopy frames '
                              '(design D13; plan S14)', 'koa_query': adql2, 'n_frames_total': total,
               'sampmode_codes': names, 'created': now, 'script': SCRIPT, 'calib_version': CALIB_VERSION}
    sm.write(OUT_SAMP, format='ascii.ecsv', overwrite=True)
    register({str(p.relative_to(DATA)): {'calib_version': CALIB_VERSION, 'created': now,
                                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'script': SCRIPT,
                                         'provenance': prov}
              for p, prov in ((OUT_CAND, f'KOA TAP census in {"/".join(filters)}, {len(fr)} public frames; '
                                         'SIMBAD A0 V<11; 2MASS J/H/Ks (II/246)'),
                              (OUT_SAMP, f'KOA TAP SAMPMODE histogram of {total} public on-sky spectroscopy frames'))})
    report(cand, sm)
    design_counts(fr)
    return 0


def per_band(cand):
    """Per filter: the counts the S23c prompt asks for; returns a list of dicts (printed by :func:`report`)."""
    rows = []
    for filt in sorted(set(str(f) for f in cand['filter']), key=lambda f: (f[0], f)):
        sub = cand[cand['filter'] == filt]
        use = sub[np.isin(sub['std_class'], USABLE) & sub['has_flats'] & sub['wide_slit']]
        red = use[use['reducible']]
        eras = {e.name: len(set(red[red['era'] == e.name]['night'])) for e in MOSFIRE.eras}
        by_night = {}
        for r in use:
            by_night.setdefault(str(r['night']), set()).add('WD' if str(r['std_class']) in ('WD', 'archive') else 'A0V')
        both = sorted(n for n, c in by_night.items() if c == {'WD', 'A0V'})
        # D52's weaker form: the same night holds a white dwarf and an A0V star on any slit (usable class, flats)
        any_slit = {}
        for r in sub[np.isin(sub['std_class'], USABLE) & sub['has_flats']]:
            any_slit.setdefault(str(r['night']), set()).add('WD' if str(r['std_class']) in ('WD', 'archive') else 'A0V')
        both_any = sorted(n for n, c in any_slit.items() if c == {'WD', 'A0V'})
        rows.append({'filter': filt, 'rows': len(sub), 'nights': len(set(sub['night'])),
                     'wide_usable_rows': len(use), 'wide_usable_nights': len(set(use['night'])),
                     'reducible_nights': len(set(red['night'])),
                     'wd': int(np.sum(use['std_class'] == 'WD')), 'archive': int(np.sum(use['std_class'] == 'archive')),
                     'a0v': int(np.sum(use['std_class'] == 'A0V')), 'stars': len(set(use['standard'])),
                     'eras': eras, 'wd_and_a0v_nights': both, 'wd_and_a0v_nights_any_slit': both_any})
    return rows


def report(cand, sm):
    print(f'\ncandidates: {len(cand)} rows (night x standard x mask x filter), '
          f'{len(set(cand["night"]))} nights, filters {sorted(set(str(f) for f in cand["filter"]))}')
    print('\nper band (usable = WD/archive/A0V with flats on a wide slit; reducible = also a wavelength calibrator):')
    print(f"{'filter':6s} {'rows':>5s} {'nights':>6s} | {'wide usable rows':>16s} {'nights':>6s} {'reducible':>9s} | "
          f"{'WD':>3s} {'arch':>4s} {'A0V':>4s} {'stars':>5s} | reducible nights per era | WD+A0V nights (wide; any slit)")
    for b in per_band(cand):
        eras = ', '.join(f'{k[:7]} {v}' for k, v in b['eras'].items())
        print(f"{b['filter']:6s} {b['rows']:5d} {b['nights']:6d} | {b['wide_usable_rows']:16d} {b['wide_usable_nights']:6d} "
              f"{b['reducible_nights']:9d} | {b['wd']:3d} {b['archive']:4d} {b['a0v']:4d} {b['stars']:5d} | {eras} | "
              f"{len(b['wd_and_a0v_nights'])} {b['wd_and_a0v_nights'][:6]}; "
              f"{len(b['wd_and_a0v_nights_any_slit'])} {b['wd_and_a0v_nights_any_slit'][:6]}")
    for cls in ('WD', 'archive', 'A0V', 'other'):
        sub = cand[cand['std_class'] == cls]
        print(f'  {cls:5s}: {len(sub)} rows, {len(set(sub["night"]))} nights, {len(set(sub["standard"]))} stars')
    print('\nrows per era and slit class (all classes; usable = WD/archive/A0V with flats):')
    print(f"{'era':18s} {'wide':>6s} {'narrow':>7s} {'wide usable':>12s} {'narrow usable':>14s}")
    for era in [e.name for e in MOSFIRE.eras]:
        sub = cand[cand['era'] == era]
        use = sub[np.isin(sub['std_class'], USABLE) & sub['has_flats']]
        print(f"{era:18s} {int(np.sum(sub['wide_slit'])):6d} {int(np.sum(~sub['wide_slit'])):7d} "
              f"{int(np.sum(use['wide_slit'])):12d} {int(np.sum(~use['wide_slit'])):14d}")
    use = cand[np.isin(cand['std_class'], USABLE) & cand['has_flats'] & cand['wide_slit']]
    print(f"public wide-slit usable standards with flats: {len(use)} rows, {len(set(use['night']))} nights, "
          f"{len(set(use['standard']))} stars (WD {int(np.sum(use['std_class'] == 'WD'))}, archive "
          f"{int(np.sum(use['std_class'] == 'archive'))}, A0V {int(np.sum(use['std_class'] == 'A0V'))})")
    red = use[use['reducible']]
    print(f"  of which reducible (a wavelength calibrator: OH frames or long2pos arcs): {len(red)} rows, "
          f"{len(set(red['night']))} nights, {len(set(red['standard']))} stars "
          f"(oh {int(np.sum(red['wavecal'] == 'oh'))}, lamp {int(np.sum(red['wavecal'] == 'lamp'))}); per era: "
          + ', '.join(f"{e.name} {len(set(red[red['era'] == e.name]['night']))}" for e in MOSFIRE.eras))
    oth = cand[(cand['std_class'] == 'other') & cand['wide_slit'] & cand['has_flats']]
    print(f"  not usable (other: HIP/HD not A0V or unclassified): wide with flats {len(oth)} rows, "
          f"{len(set(oth['night']))} nights")
    nights = sorted(set(cand['night']))
    with_arcs = {n for n, m in zip(cand['night'], cand['lamp_arcs_match']) if m}
    print(f'candidate nights with matching lamp arcs: {len(with_arcs)} of {len(nights)} '
          f'({100 * len(with_arcs) / max(len(nights), 1):.1f}%)')
    print('\nSAMPMODE census (public on-sky spectroscopy frames):')
    for r in sm:
        print(f"  {r['mode']:6s} NUMREADS {r['numreads']:4d}: {r['n_frames']:7d} ({100 * r['fraction']:.2f}%)")
    by_mode = {}
    for r in sm:
        by_mode[r['mode']] = by_mode.get(r['mode'], 0) + float(r['fraction'])
    print('  by mode: ' + ', '.join(f'{m} {100 * f:.2f}%' for m, f in sorted(by_mode.items())))
    if 'J2' in set(str(f) for f in cand['filter']):
        chk = cand[(cand['night'] == '20220409') & (cand['filter'] == 'J2')]
        ok = any(('MF.20220409.55932' in r['koaids'] and 'MF.20220409.56084' in r['koaids'] and r['wide_slit'])
                 for r in chk)
        print(f"\ncheck 2022-04-09: {[(r['standard'], r['maskname'], r['wide_slit'], r['koaids']) for r in chk]} -> "
              f"{'PASS' if ok else 'FAIL'}")


def design_counts(fr):
    """The design 9.2 TAP counts recomputed from the cached frames, against :data:`DESIGN_COUNTS`.

    Per filter: long-slit + long2pos frames; distinct ``date_obs`` with a
    star-like target name (:data:`STAR_PREFIXES`, as the survey's SQL
    ``LIKE``); ``long2pos_specphot`` such nights. The survey counted
    ``date_obs`` (UT dates), not census nights, and ran on a different day:
    KOA's public set grows as proprietary periods end, so later counts are
    expected to be equal or larger.
    """
    print('\ndesign 9.2 TAP counts from the cached frames (frames, star-named UT dates, long2pos_specphot star dates):')
    targ = np.array([str(x).strip() for x in fr['targname']])
    star = np.array([any(t.startswith(p) for p in STAR_PREFIXES) for t in targ])
    l2p = np.array(['long2pos_specphot' in str(m) for m in fr['maskname']])
    dates = np.array([str(d)[:10] for d in fr['date_obs']])
    for filt in sorted(set(str(f) for f in fr['filter']), key=lambda f: (f[0], f)):
        s = np.asarray(fr['filter']).astype(str) == filt
        got = (int(s.sum()), len(set(dates[s & star])), len(set(dates[s & star & l2p])))
        ref = DESIGN_COUNTS.get(filt)
        verdict = '' if ref is None else (' = design 9.2' if got == ref else f' vs design 9.2 {ref}')
        print(f'  {filt:3s} {got[0]:6d} {got[1]:5d} {got[2]:4d}{verdict}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--refresh', action='store_true', help='re-run the queries instead of using the cache')
    p.add_argument('--filters', nargs='+', default=['J'], metavar='BAND',
                   help='band groups (Y, J = J/J2/J3, H, K) or KOA filter names; default J (the S14 census)')
    a = p.parse_args()
    sys.exit(main(a.refresh, tuple(a.filters)))
