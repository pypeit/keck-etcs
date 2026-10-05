#!/usr/bin/env python
"""Download one MOSFIRE night's raw frames from KOA, locally or into the bucket (plan S14b; design D37, 4.2).

Usage:
    python scripts/koa/download_mosfire_night.py --manifest nautilus/manifests/nights_pilot.csv [--index N]
        [--lamp-arcs] [--to-s3]
    python scripts/koa/download_mosfire_night.py 20241230 [20250723 ...] [--lamp-arcs] [--to-s3]
    python scripts/koa/download_mosfire_night.py --collect JOB_NAME [--to-s3]

For each night (a night-manifest row: ``standard``, ``slit`` = mask, ``filter``,
``std_ra``, ``std_dec``; positional nights take their row from
``keck_etcs/data/mosfire/koa_standards_candidates.ecsv``) the script asks KOA's
TAP service for every MOSFIRE frame of the night (UT date of UT + 6 h, as in
``search_mosfire_standards.py``) and selects:

- ``standard``: on-sky frames with the night's filter and mask, within 60" of
  the standard;
- ``dome_flat``: dome flats with that filter, on the standard's mask if any,
  else on the OH frames' mask, else on any mask of the same kind (LONGSLIT or
  long2pos). One mask only, so PypeIt does not trace a mixture of slit widths.
  KOA cannot tell lamp-on from lamp-off flats; ``reduce_standard.py`` checks
  the headers;
- ``oh_arc`` (LONGSLIT standards): up to 6 narrow-slit (< 3") on-sky frames of
  the same filter and at least 55 s (short telluric exposures show too little
  OH), not the standard, on their most common mask, nearest in
  time to the standard. A wide slit broadens the standard's own OH lines too
  much; the driver types these frames ``arc,tilt``. Frames of the
  Hennawi/Yang/Wang programs are marked ``priority`` (validation candidates,
  KOA prompt 3);
- ``lamp_arc``: for ``long2pos_specphot`` standards, every Ne/Ar arc of the
  filter on a long2pos mask (PypeIt's wavelength calibration for that mask;
  required); with ``--lamp-arcs`` (the user's choice after the prompt 1
  census), also the arcs on the standard's mask on any night, for the
  calibration monitor (D44).

A night with no standard frames is ``no standard``; one without dome flats,
or without a wavelength calibrator (OH frames, or long2pos arcs for
specphot), is ``no calibs``. Nothing is downloaded for either.

Frames are fetched over plain HTTP (KOA's ``nph-getKOA`` with the frame's
``filehand``; no ``pykoa``) into ``$KECK_ETCS_DATA/mosfire/<night>/raw/<ofname>``
(the original file name, as the dev-suite frames), checked to be FITS, and
listed in ``raw/manifest.ecsv`` (``koaid, file, frame_type, target, slit,
filter, sampmode, numreads, exptime, airmass, ut, mjd, size, sha256, progid,
priority``). Idempotent: a frame already in the manifest with the same size
on disk (or, with ``--to-s3``, in the bucket) is not fetched again. With
``--to-s3`` the raw directory is pushed to ``s3://keck-etcs/mosfire/<night>/raw/``
(``scripts/nautilus/s3_sync.py``, skipping same-size objects) and the bucket
sizes are checked against the manifest.

Each night writes a status row to
``$KECK_ETCS_DATA/runs/<JOB_NAME>/download_status/<index>_<night>.ecsv``
(pushed with ``--to-s3``); ``--collect JOB_NAME`` concatenates them into
``runs/<JOB_NAME>/download_status.ecsv``. Only public data: KOA's anonymous
TAP returns public frames only. Standard library plus astropy (runs in the
image). Exit codes: 0 success or nothing to do; 10 no calibs; 11 no standard;
16 download failed; 17 push failed.
"""
import argparse
import csv
import datetime
import hashlib
import io
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table, vstack

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from keck_etcs import paths  # noqa: E402
import search_mosfire_standards as census  # noqa: E402

KOA_TAP = 'https://koa.ipac.caltech.edu/TAP/sync'
KOA_GET = 'https://koa.ipac.caltech.edu/cgi-bin/getKOA/nph-getKOA'
COLUMNS = tuple(c for c in census.COLUMNS if c != 'object') + ('filehand', 'ofname', 'filesize_mb')
MAX_OH = 6
EXIT = {'success': 0, 'skipped': 0, 'no calibs': 10, 'no standard': 11, 'download failed': 16, 'push failed': 17}
S3_SYNC = REPO / 'scripts' / 'nautilus' / 's3_sync.py'
UA = {'User-Agent': 'keck-etcs KOA download (github.com/pypeit/keck-etcs)'}


def http(url, data=None, timeout=600, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:  # noqa: BLE001 - network: retry with backoff
            if k == tries - 1:
                raise
            time.sleep(5 * 2 ** k)


def night_frames(night):
    """Every public MOSFIRE frame of the night (KOA TAP, VOTable)."""
    d = datetime.date(int(night[:4]), int(night[4:6]), int(night[6:]))
    prev = (d - datetime.timedelta(days=1)).strftime('%Y%m%d')
    adql = (f"SELECT {', '.join(COLUMNS)} FROM koa_mosfire WHERE koaid LIKE 'MF.{night}%' "
            f"OR koaid LIKE 'MF.{prev}%'")
    body = http(KOA_TAP, {'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'votable', 'QUERY': adql})
    if b'Failed to execute' in body[:3000] or (b'QUERY_STATUS' in body[:3000] and b'value="ERROR"' in body[:3000]):
        raise RuntimeError(f'KOA TAP error: {body[:1500]!r}')
    t = Table.read(io.BytesIO(body), format='votable')
    t['night'] = [census.night_of(dd, u) for dd, u in zip(t['date_obs'], t['ut'])]
    return t[t['night'] == night]


def select_frames(fr, row, lamp_arcs=False):
    """``[(frame row, frame_type, priority)]`` and a status for one manifest row (see the docstring)."""
    filt, mask = str(row['filter']), str(row['slit'])
    on, dome, arc = census.frame_classes(fr)
    l2p = 'long2pos' in mask
    specphot = 'long2pos_specphot' in mask
    sep = SkyCoord(fr['ra'], fr['dec'], unit='deg').separation(
        SkyCoord(float(row['std_ra']), float(row['std_dec']), unit='deg')).arcsec
    f_ok = np.array([str(f) == filt for f in fr['filter']])
    masks = np.array([str(m) for m in fr['maskname']])
    kind = np.array([('long2pos' in m) == l2p for m in masks])
    std = on & f_ok & (masks == mask) & (sep <= census.MATCH_ARCSEC)
    if not std.any():
        return [], 'no standard'
    t_std = float(np.median(np.asarray(fr['mjd_obs'], float)[std]))
    pick = [(i, 'standard') for i in np.flatnonzero(std)]
    oh_mask = None
    if not l2p:
        narrow = np.array(['LONGSLIT' in m and census.slit_of(m)[0] < census.WIDE_SLIT for m in masks])
        longexp = np.asarray(fr['truitime'], float) >= census.MIN_OH_EXPTIME
        cand = np.flatnonzero(on & f_ok & narrow & longexp & (sep > census.MATCH_ARCSEC))
        if len(cand):
            vals, counts = np.unique(masks[cand], return_counts=True)
            oh_mask = vals[np.argmax(counts)]
            cand = [i for i in cand if masks[i] == oh_mask]
            cand = sorted(cand, key=lambda i: abs(float(fr['mjd_obs'][i]) - t_std))[:MAX_OH]
            pick += [(i, 'oh_arc') for i in sorted(cand)]
    flats = dome & f_ok & kind
    for m in (mask, oh_mask):
        if m is not None and (flats & (masks == m)).any():
            flats = flats & (masks == m)
            break
    else:
        if flats.any():   # one mask only: the most common
            vals, counts = np.unique(masks[flats], return_counts=True)
            flats = flats & (masks == vals[np.argmax(counts)])
    pick += [(i, 'dome_flat') for i in np.flatnonzero(flats)]
    arcs = set()
    if specphot:
        arcs |= set(np.flatnonzero(arc & f_ok & np.array(['long2pos' in m for m in masks])))
    if lamp_arcs:
        arcs |= set(np.flatnonzero(arc & f_ok & (masks == mask)))
    pick += [(i, 'lamp_arc') for i in sorted(arcs)]
    if not flats.any():
        return pick, 'no calibs'
    if (specphot and not any(k == 'lamp_arc' for _, k in pick)) or (not l2p and oh_mask is None):
        return pick, 'no calibs'
    pis = lambda i: str(fr['progpi'][i]).lower()
    return [(fr[i], k, any(p in pis(i) for p in census.PRIORITY_PI)) for i, k in pick], 'ok'


def s3_sizes(prefix):
    """``{key: size}`` under a bucket prefix (``s3_sync.py ls``)."""
    r = subprocess.run([sys.executable, str(S3_SYNC), 'ls', prefix], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f's3_sync.py ls {prefix} failed: {r.stderr[-500:]}')
    out = {}
    for ln in r.stdout.splitlines():
        p = ln.split()
        if len(p) >= 2 and p[0].isdigit() and p[1].startswith(prefix):
            out[p[1]] = int(p[0])
    return out


def status_row(job, index, night, status, error='', **counts):
    row = {'job_name': job, 'index': int(index), 'night': night, 'status': status, 'error': (error or '')[:500],
           **counts, 'pod': os.environ.get('POD_NAME', ''), 'node': os.environ.get('NODE_NAME', ''),
           'image': os.environ.get('KECK_ETCS_IMAGE', 'local'),
           'time': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    out = paths.data_root() / 'runs' / job / 'download_status' / f'{int(index):04d}_{night}.ecsv'
    out.parent.mkdir(parents=True, exist_ok=True)
    Table(rows=[row]).write(out, format='ascii.ecsv', overwrite=True)
    return out


def download_night(row, index=0, lamp_arcs=False, to_s3=False, job=None):
    import keck_etcs
    job = job or os.environ.get('JOB_NAME') or 'local-download'
    night = str(row['night'])
    prefix = f'mosfire/{night}/raw'
    raw = paths.data_root() / prefix
    raw.mkdir(parents=True, exist_ok=True)
    counts = {'n_standard': 0, 'n_dome_flat': 0, 'n_oh_arc': 0, 'n_lamp_arc': 0, 'n_downloaded': 0,
              'n_skipped': 0, 'bytes_downloaded': 0, 'bytes_total': 0}

    def finish(status, error=''):
        p = status_row(job, index, night, status, error, **counts)
        if to_s3:
            subprocess.run([sys.executable, str(S3_SYNC), 'push', f'runs/{job}/download_status', '--force'],
                           capture_output=True)
        print(f"{night}: {status}{' (' + error + ')' if error else ''}; " + ', '.join(f'{k} {v}' for k, v in counts.items()))
        return EXIT[status]

    fr = night_frames(night)
    picks, verdict = select_frames(fr, row, lamp_arcs)
    for _, k, *_ in picks:
        counts[f'n_{k}'] = counts.get(f'n_{k}', 0) + 1
    if verdict != 'ok':
        return finish(verdict, f'{len(fr)} KOA frames that night; selection: '
                      + ', '.join(f'{k} {counts["n_" + k]}' for k in ('standard', 'dome_flat', 'oh_arc', 'lamp_arc')))

    man_path = raw / 'manifest.ecsv'
    have = {}
    if to_s3:
        sizes = s3_sizes(prefix)
        if f'{prefix}/manifest.ecsv' in sizes:
            subprocess.run([sys.executable, str(S3_SYNC), 'pull', f'mosfire/{night}', '--include', 'raw/manifest.ecsv',
                            '--force'], capture_output=True)
    if man_path.exists():
        have = {str(r['koaid']): r for r in Table.read(man_path, format='ascii.ecsv')}
    rows = []
    for fr_row, kind, prio in picks:
        koaid, fname = str(fr_row['koaid']), str(fr_row['ofname'])
        dst = raw / fname
        old = have.get(koaid)
        present = old is not None and ((to_s3 and sizes.get(f'{prefix}/{fname}') == int(old['size']))
                                       or (dst.exists() and dst.stat().st_size == int(old['size'])))
        if present:
            size, sha = int(old['size']), str(old['sha256'])
            counts['n_skipped'] += 1
        else:
            try:
                data = http(f"{KOA_GET}?filehand={urllib.parse.quote(str(fr_row['filehand']))}")
            except Exception as exc:  # noqa: BLE001
                return finish('download failed', f'{koaid}: {exc}')
            if not data.startswith(b'SIMPLE'):
                return finish('download failed', f'{koaid}: not a FITS file ({data[:80]!r})')
            dst.write_bytes(data)
            size, sha = len(data), hashlib.sha256(data).hexdigest()
            counts['n_downloaded'] += 1
            counts['bytes_downloaded'] += size
        counts['bytes_total'] += size
        rows.append({'koaid': koaid, 'file': fname, 'frame_type': kind, 'target': str(fr_row['targname']),
                     'slit': str(fr_row['maskname']), 'filter': str(fr_row['filter']),
                     'sampmode': int(fr_row['sampmode']), 'numreads': int(fr_row['numreads']),
                     'exptime': float(fr_row['truitime']), 'airmass': float(fr_row['airmass']),
                     'ut': str(fr_row['ut']), 'mjd': float(fr_row['mjd_obs']), 'size': size, 'sha256': sha,
                     'progid': str(fr_row['progid']), 'priority': bool(prio)})
    man = Table(rows=rows)
    man.meta = {'description': 'KOA raw frames of one MOSFIRE night for the keck-etcs reductions (plan S14b)',
                'night': night, 'standard': str(row['standard']), 'std_class': str(row.get('std_class', '')),
                'mask': str(row['slit']), 'filter': str(row['filter']), 'lamp_arcs_option': bool(lamp_arcs),
                'source': f'{KOA_TAP} + {KOA_GET} (public frames only)', 'keck_etcs_version': keck_etcs.__version__,
                'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'script': 'scripts/koa/download_mosfire_night.py'}
    man.write(man_path, format='ascii.ecsv', overwrite=True)
    if to_s3:
        r1 = subprocess.run([sys.executable, str(S3_SYNC), 'push', prefix], capture_output=True, text=True)
        r2 = subprocess.run([sys.executable, str(S3_SYNC), 'push', f'mosfire/{night}', '--include', 'raw/manifest.ecsv',
                             '--force'], capture_output=True, text=True)
        if r1.returncode or r2.returncode:
            return finish('push failed', (r1.stderr + r2.stderr)[-400:])
        sizes = s3_sizes(prefix)
        bad = [r['file'] for r in rows if sizes.get(f"{prefix}/{r['file']}") != r['size']]
        if bad:
            return finish('push failed', f'bucket sizes differ from the manifest for {bad[:5]}')
    return finish('success' if counts['n_downloaded'] else 'skipped')


def manifest_rows(path, index=None):
    rows = list(csv.DictReader(open(path)))
    return [(i, r) for i, r in enumerate(rows) if index is None or i == int(index)]


def rows_for_nights(nights):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_night_manifest as mm
    t = Table.read(mm.CAND, format='ascii.ecsv')
    out = []
    for k, n in enumerate(nights):
        sub = [r for r in t if str(r['night']) == str(n)]
        if not sub:
            raise SystemExit(f'{n}: not in the candidate table')
        out.append((k, mm.manifest_row(mm.best(sub))))
    return out


def collect(job, to_s3=False):
    d = paths.data_root() / 'runs' / job / 'download_status'
    if to_s3:
        subprocess.run([sys.executable, str(S3_SYNC), 'pull', f'runs/{job}/download_status', '--force'],
                       capture_output=True)
    files = sorted(d.glob('*.ecsv'))
    if not files:
        print(f'no status rows in {d}')
        return 1
    t = vstack([Table.read(f, format='ascii.ecsv') for f in files])
    out = d.parent / 'download_status.ecsv'
    t.write(out, format='ascii.ecsv', overwrite=True)
    vals, counts = np.unique(np.asarray(t['status']), return_counts=True)
    print(f'{out}: {len(t)} nights; ' + ', '.join(f'{v} {c}' for v, c in zip(vals, counts))
          + f"; {np.sum(t['bytes_total']) / 1e9:.2f} GB in the manifests, "
          f"{np.sum(t['bytes_downloaded']) / 1e9:.2f} GB downloaded")
    return 0


def main(a):
    if a.collect:
        return collect(a.collect, a.to_s3)
    todo = manifest_rows(a.manifest, a.index) if a.manifest else rows_for_nights(a.nights)
    worst = 0
    for i, row in todo:
        rc = download_night(row, i, a.lamp_arcs, a.to_s3)
        worst = worst or rc
    return worst


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('nights', nargs='*', help='nights YYYYMMDD (row from the candidate table)')
    p.add_argument('--manifest', help='night manifest CSV')
    p.add_argument('--index', help='only this row of the manifest (JOB_COMPLETION_INDEX)')
    p.add_argument('--lamp-arcs', action='store_true', help="also the Ne/Ar arcs on the standard's mask (D44)")
    p.add_argument('--to-s3', action='store_true', help='push raw/ to s3://keck-etcs/mosfire/<night>/raw/')
    p.add_argument('--collect', metavar='JOB_NAME', help='concatenate the status rows of a job')
    a = p.parse_args()
    if not (a.nights or a.manifest or a.collect):
        p.error('give nights, --manifest or --collect')
    sys.exit(main(a))
