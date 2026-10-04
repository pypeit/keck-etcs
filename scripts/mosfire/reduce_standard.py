#!/usr/bin/env python
"""Reduce one MOSFIRE long-slit night with PypeIt: the local reference and the in-pod driver.

Usage:
    python scripts/mosfire/reduce_standard.py DATE [options]

e.g. ``reduce_standard.py 20220409 --save-pypeit
scripts/mosfire/pypeit_files/keck_mosfire_20220409_J2.pypeit``.

Steps (each failure class has its own exit code, design 4.8.6):

 0. PypeIt pin check (``scripts/check_pypeit_pin.py``, design D35); its JSON
    is copied into ``run_manifest.json``. A failed check stops the run
    unless ``--skip-pin-check``.
 1. ``--s3-pull``: pull ``<instrument>/<DATE>/raw`` from the bucket first.
 2. ``pypeit_setup -s keck_mosfire -r raw/ -d redux/setup_files -c all``.
 3. Patch: merge the setups of the chosen filter into one PypeIt file (the
    46x1 science and 46x5 standard long slits share the spatial slit edges,
    so the standard uses the night's flats and the science frames' OH lines,
    as in the dev-suite template); retype every frame from its header (below);
    pair nod frames of the same target and slit in time order, each A with
    the next B (ABBA -> AB, BA), both ways (``comb_id``/``bkg_id``, one
    spec1d per frame); a leftover frame uses the nearest opposite frame; apply the reduction parameter block (``--par``, default
    :data:`DEFAULT_PAR`, from the dev-suite ``keck_mosfire_j2_long.pypeit``).
 4. ``run_pypeit <file> -r redux/ -o``.
 5. Check that every science and standard frame has a spec1d with at least
    one object; report FWHM, S/N and the wavelength RMS.
 6. ``--sens FILE``: ``pypeit_sensfunc`` on each standard spec1d into
    ``sens/sens_<spec1d stem>.fits``.
 7. Write ``<night>/run_manifest.json`` (design 4.8.5), on failure too.
 8. ``--s3-push PREFIX``: push ``$data_root/PREFIX`` to the bucket.

Frame typing. PypeIt's MOSFIRE rule keys on ``FLATSPEC``, which is 1 in
every frame of 2022-04-09 (science and standard included), so every frame
comes out as a flat. This driver types from the dome-lamp and telescope
cards instead:

- ``FLAMP1`` or ``FLAMP2 == 'on'`` -> ``pixelflat,illumflat,trace``;
- lamps off and ``TARGNAME`` contains "FLAT", or the telescope is parked
  (``AXESTAT`` neither ``tracking`` nor ``slewing``; nodded frames read
  ``slewing``) -> ``lampoffflats``;
- on sky, at a spectrophotometric standard's position
  (``pypeit.core.standard.get_archive_standard(check=True)``) -> ``standard``,
  whatever the exposure time (PypeIt types standards by ``exptime < 20 s``);
- other on-sky frames -> ``arc,science,tilt`` (OH lines as the arc).

Paths come from arguments or ``KECK_ETCS_DATA``; nothing is interactive.
``--scratch DIR`` uses DIR as the data root for the whole run (raw frames
pulled or linked there, reduction written there), as a pod does on its
``emptyDir``.

Exit codes: 0 success; 10 no calibs; 11 setup failed; 12 reduce failed;
13 no trace; 14 sens failed; 15 pin check failed; 16 pull failed;
17 push failed.
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[2]
INSTRUMENT = 'mosfire'
SPECTROGRAPH = 'keck_mosfire'

EXIT = {'success': 0, 'no calibs': 10, 'setup failed': 11, 'reduce failed': 12,
        'no trace': 13, 'sens failed': 14, 'pin check failed': 15, 'pull failed': 16,
        'push failed': 17}

# From the dev-suite pypeit_files/keck_mosfire_j2_long.pypeit (PypeIt 1.8)
DEFAULT_PAR = """[calibrations]
  [[flatfield]]
    tweak_slits = False
  [[slitedges]]
    fit_min_spec_length = 0.3
[reduce]
  [[findobj]]
    find_trim_edge = 10,10
    snr_thresh = 80.
"""


class StageError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def run(cmd, log, env=None, cwd=None):
    """Run a command, tee its output to ``log``; return the exit code."""
    print(f'$ {" ".join(str(c) for c in cmd)}', flush=True)
    with open(log, 'a') as f:
        f.write(f'\n$ {" ".join(str(c) for c in cmd)}\n')
        f.flush()
        proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env=env, cwd=cwd)
        for line in proc.stdout:
            f.write(line)
        return proc.wait()


def keck_etcs_git():
    """keck_etcs SHA (``keck_etcs.provenance``, which prefers ``KECK_ETCS_GIT_SHAS``)
    and whether the local work tree is dirty (None inside the image)."""
    from keck_etcs import provenance
    sha = provenance.git_shas()['keck_etcs']
    res = subprocess.run(['git', '-C', str(REPO), 'status', '--porcelain'],
                         capture_output=True, text=True)
    # Untracked files count: the driver itself may not be committed yet
    dirty = (res.stdout.strip() != '') if res.returncode == 0 else None
    return sha, dirty


def provenance_image():
    from keck_etcs import provenance
    return provenance.image_info()


# ---------------------------------------------------------------- frame typing

def classify(hdr, ra, dec):
    """Frame type from the dome-lamp and telescope cards (see module docstring).

    ``ra``, ``dec`` (deg) are PypeIt's metadata values for the frame.
    """
    from pypeit.core import standard
    lamp_on = any(str(hdr.get(k, '')).strip().lower() == 'on' for k in ('FLAMP1', 'FLAMP2'))
    if lamp_on:
        return 'pixelflat,illumflat,trace'
    on_sky = str(hdr.get('AXESTAT', '')).strip().lower() in ('tracking', 'slewing')
    if not on_sky or 'FLAT' in str(hdr.get('TARGNAME', '')).upper():
        return 'lampoffflats'
    if standard.get_archive_standard(float(ra), float(dec), check=True):
        return 'standard'
    return 'arc,science,tilt'


def pair_nods(tbl):
    """Set ``comb_id``/``bkg_id`` for A/B nods (see module docstring); return problems."""
    tbl['comb_id'] = -1
    tbl['bkg_id'] = -1
    onsky = np.array([('science' in t) or ('standard' in t) for t in tbl['frametype']])
    pos = np.array([str(p).strip() for p in tbl['dithpos']])
    mjd = np.array(tbl['mjd'], dtype=float)
    for i in np.where(onsky)[0]:
        tbl['comb_id'][i] = i
    problems = []
    groups = {}
    for i in np.where(onsky)[0]:
        groups.setdefault((str(tbl['target'][i]), str(tbl['decker'][i])), []).append(i)
    for (target, _decker), idx in groups.items():
        idx = sorted(idx, key=lambda k: mjd[k])
        bad = [tbl['filename'][k] for k in idx if pos[k] not in ('A', 'B')]
        if bad:
            problems.append(f'{target}: dithpos not A/B for {bad}')
            continue
        paired, k = set(), 0
        while k < len(idx) - 1:
            a, b = idx[k], idx[k + 1]
            if pos[a] != pos[b]:
                tbl['bkg_id'][a], tbl['bkg_id'][b] = tbl['comb_id'][b], tbl['comb_id'][a]
                paired.update((a, b))
                k += 2
            else:
                k += 1
        for a in idx:
            if a in paired:
                continue
            opp = [b for b in idx if pos[b] != pos[a]]
            if not opp:
                problems.append(f'{tbl["filename"][a]}: no opposite nod of {target}')
                continue
            b = min(opp, key=lambda j: abs(mjd[j] - mjd[a]))
            tbl['bkg_id'][a] = tbl['comb_id'][b]
    return problems


def build_pypeit_file(setup_dir, out_file, filt, par_text, raw_dir):
    """Merge and patch the pypeit_setup output; return (path, table, notes)."""
    from pypeit.inputfiles import PypeItFile

    files = sorted(Path(setup_dir).glob('*/*.pypeit'))
    if not files:
        raise StageError('setup failed', f'pypeit_setup wrote no .pypeit file in {setup_dir}')
    tables, setups = [], {}
    for f in files:
        pf = PypeItFile.from_file(str(f), vet=False)
        t = Table(pf.data)
        t['setup_name'] = f.stem
        tables.append(t)
        setups[f.stem] = pf.setup
    from astropy.table import vstack
    tbl = vstack(tables, metadata_conflicts='silent')
    filters = sorted(set(tbl['filter1']))
    if filt is None:
        if len(filters) != 1:
            raise StageError('setup failed', f'several filters {filters}; choose one with --filter')
        filt = filters[0]
    tbl = tbl[tbl['filter1'] == filt]
    if len(tbl) == 0:
        raise StageError('setup failed', f'no frames with filter {filt} (have {filters})')

    notes = []
    old = list(tbl['frametype'])
    tbl['frametype'] = [classify(fits.getheader(Path(raw_dir) / fn), ra, dec)
                        for fn, ra, dec in zip(tbl['filename'], tbl['ra'], tbl['dec'])]
    for fn, o, n in zip(tbl['filename'], old, tbl['frametype']):
        if o != n:
            notes.append(f'{fn}: frametype {o} -> {n}')
    types = list(tbl['frametype'])
    if not any('pixelflat' in t for t in types):
        raise StageError('no calibs', f'no lamp-on flats with filter {filt}')
    if not any('arc' in t for t in types):
        raise StageError('no calibs', 'no on-sky frames to serve as OH arcs')
    if not any(('science' in t) or ('standard' in t) for t in types):
        raise StageError('setup failed', 'no science or standard frames')

    tbl['calib'] = ['all' if ('flat' in t) else '1' for t in types]
    tbl.sort('mjd')
    problems = pair_nods(tbl)
    if problems:
        raise StageError('setup failed', 'nod pairing: ' + '; '.join(problems))

    keep = [c for c in tbl.colnames if c != 'setup_name']
    setup_names = sorted(set(tbl['setup_name']))
    # PypeItFile.setup is flat: {'Setup A': None, 'dispname': ..., 'slitwid': ...}
    first = setups[setup_names[0]]
    setup_block = {'Setup A': None, **{k: v for k, v in first.items()
                                       if not k.startswith('Setup')}} if first else None
    if len(setup_names) > 1:
        widths = sorted({str(setups[n].get('slitwid')) for n in setup_names if setups[n]})
        notes.append(f'merged pypeit_setup setups {setup_names} into one '
                     f'(slitwid {widths}; the setup block keeps {setup_names[0]}\'s values)')
    cfg = [f'[rdx]', f'  spectrograph = {SPECTROGRAPH}'] + par_text.strip().splitlines()
    pf = PypeItFile(config=cfg, file_paths=[str(raw_dir)], data_table=tbl[keep],
                    setup=setup_block, vet=False)
    pf.write(str(out_file))
    return Path(out_file), tbl[keep], notes, filt


# ---------------------------------------------------------------- QA

def wave_qa(redux):
    from pypeit.wavecalib import WaveCalib
    out = []
    for f in sorted((redux / 'Calibrations').glob('WaveCalib_*.fits')):
        wc = WaveCalib.from_file(str(f), chk_version=False)
        for k, wf in enumerate(wc.wv_fits):
            if wf is None or wf.pypeitfit is None:
                out.append({'file': f.name, 'slit': k, 'rms_pix': None, 'pass': False})
                continue
            thresh = 0.11 * wf.fwhm if wf.fwhm is not None else None
            out.append({'file': f.name, 'slit': int(wc.spat_ids[k]), 'rms_pix': float(wf.rms),
                        'fwhm_pix': None if wf.fwhm is None else float(wf.fwhm),
                        'rms_thresh_pix': None if thresh is None else float(thresh),
                        'pass': bool(thresh is None or wf.rms < thresh)})
    return out


def spec1d_qa(redux, tbl, platescale):
    from pypeit.specobjs import SpecObjs
    rows, missing = [], []
    for row in tbl:
        if not (('science' in row['frametype']) or ('standard' in row['frametype'])):
            continue
        stem = Path(row['filename']).stem
        hits = sorted((redux / 'Science').glob(f'spec1d_{stem}-*.fits'))
        if not hits:
            missing.append(row['filename'])
            continue
        sobjs = SpecObjs.from_fitsfile(str(hits[0]), chk_version=False)
        if len(sobjs) == 0:
            missing.append(row['filename'])
        for so in sobjs:
            fwhm = None if so['FWHM'] is None else float(so['FWHM'])
            rows.append({'frame': row['filename'], 'spec1d': hits[0].name,
                         'frametype': row['frametype'], 'target': str(row['target']),
                         'name': so['NAME'], 'spat_pixpos': float(so['SPAT_PIXPOS']),
                         'fwhm_pix': fwhm,
                         'fwhm_arcsec': None if fwhm is None else fwhm * platescale,
                         's2n': None if so['S2N'] is None else float(so['S2N']),
                         'sign': 'positive' if np.nanmedian(so['OPT_COUNTS'] if so['OPT_COUNTS'] is not None
                                                            else so['BOX_COUNTS']) > 0 else 'negative'})
    return rows, missing


# ---------------------------------------------------------------- main

def main(args):
    t0 = time.time()
    timings = {}
    started = utcnow()
    root = Path(args.scratch).resolve() if args.scratch else paths.data_root()
    env = dict(os.environ, KECK_ETCS_DATA=str(root), MPLBACKEND='Agg')
    date = str(args.date)
    night = root / INSTRUMENT / date
    raw = night / 'raw'
    redux = night / 'redux'
    sens_dir = night / 'sens'
    redux.mkdir(parents=True, exist_ok=True)
    log = night / 'run.log'
    s3_sync = REPO / 'scripts' / 'nautilus' / 's3_sync.py'

    import pypeit
    kgit, kdirty = keck_etcs_git()
    import keck_etcs
    manifest = {
        'status': None, 'error': None,
        **provenance_image(),
        'pypeit_version': pypeit.__version__,
        'pypeit_git_sha': None, 'pypeit_pin': None, 'pin_check': None,
        'keck_etcs_version': keck_etcs.__version__,
        'keck_etcs_git_sha': kgit, 'keck_etcs_git_dirty': kdirty,
        'job_name': os.environ.get('JOB_NAME'),
        'pod': os.environ.get('POD_NAME') or (socket.gethostname() if os.environ.get('KUBERNETES_SERVICE_HOST') else None),
        'node': os.environ.get('NODE_NAME'),
        'host': socket.gethostname(), 'python': platform.python_version(),
        'started': started, 'finished': None,
        'instrument': SPECTROGRAPH, 'night': date,
        's3_prefix': paths.s3_prefix(INSTRUMENT, date),
        'data_root': str(root), 'command': sys.argv,
        'filter': None, 'par_block': None, 'patch_notes': [],
        'raw_sha256': {}, 'product_sha256': {}, 'pypeit_file': None, 'pypeit_file_text': None,
        'frames': [], 'wave_qa': [], 'objects': [], 'sensfuncs': [], 'gates': None, 'monitor': None,
        'timings_s': timings,
    }

    starts = {}

    def stage(name):
        # timings[name] is the stage duration (s), filled in as the next stage starts
        now = time.time()
        if starts:
            last = list(starts)[-1]
            timings[last] = round(now - starts[last], 1)
        starts[name] = now
        print(f'=== {name} {utcnow()} ===', flush=True)
        with open(log, 'a') as f:
            f.write(f'\n=== {name} {utcnow()} ===\n')

    status = 'success'
    try:
        # 0. pin check
        stage('pin_check')
        pin_json = night / 'pypeit_pin_check.json'
        rc = run([sys.executable, REPO / 'scripts' / 'check_pypeit_pin.py', '--json', pin_json],
                 log, env=env)
        if pin_json.exists():
            pj = json.loads(pin_json.read_text())
            manifest.update({k: pj.get(k) for k in ('pypeit_git_sha', 'pypeit_pin', 'pin_check')})
        if rc != 0 and not args.skip_pin_check:
            raise StageError('pin check failed', f'check_pypeit_pin.py exit {rc}; see {pin_json}')

        # 1. pull
        if args.s3_pull:
            stage('s3_pull')
            rc = run([sys.executable, s3_sync, 'pull', paths.s3_prefix(INSTRUMENT, date, 'raw')],
                     log, env=env)
            if rc != 0:
                raise StageError('pull failed', f's3_sync.py pull exit {rc}')
        elif args.link_raw_from:
            raw.mkdir(parents=True, exist_ok=True)
            for f in sorted(Path(args.link_raw_from).glob('*.fits')):
                if not (raw / f.name).exists():
                    (raw / f.name).symlink_to(f.resolve())
        frames = sorted(raw.glob('*.fits'))
        if not frames:
            raise StageError('no calibs', f'no raw frames in {raw}')
        manifest['raw_sha256'] = {f.name: sha256sum(f) for f in frames}

        # 2. setup
        stage('pypeit_setup')
        setup_dir = redux / 'setup_files'
        if setup_dir.exists():
            shutil.rmtree(setup_dir)
        rc = run(['pypeit_setup', '-s', SPECTROGRAPH, '-r', raw, '-d', setup_dir, '-c', 'all'],
                 log, env=env)
        if rc != 0:
            raise StageError('setup failed', f'pypeit_setup exit {rc}')

        # 3. patch
        stage('patch')
        par_text = Path(args.par).read_text() if args.par else DEFAULT_PAR
        manifest['par_block'] = par_text
        pfile = redux / f'{SPECTROGRAPH}_{date}.pypeit'
        pfile, tbl, notes, filt = build_pypeit_file(setup_dir, pfile, args.filter, par_text, raw)
        manifest['filter'] = filt
        manifest['patch_notes'] = notes
        manifest['pypeit_file'] = pfile.name
        manifest['pypeit_file_text'] = pfile.read_text()
        manifest['frames'] = [{c: (v.item() if hasattr(v, 'item') else v) for c, v in zip(
            ('filename', 'frametype', 'target', 'decker', 'dithpos', 'exptime', 'airmass',
             'calib', 'comb_id', 'bkg_id'),
            [row[c] for c in ('filename', 'frametype', 'target', 'decker', 'dithpos', 'exptime',
                              'airmass', 'calib', 'comb_id', 'bkg_id')])} for row in tbl]
        for n in notes:
            print(f'  {n}')
        if args.save_pypeit:
            dst = Path(args.save_pypeit)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(pfile.read_text().replace(str(raw), 'PATH_TO_RAW_DATA'))
            print(f'  saved {dst} (raw path -> PATH_TO_RAW_DATA)')
        if args.setup_only:
            status = 'success'
            return 0

        # 4. reduce
        stage('run_pypeit')
        rc = run(['run_pypeit', pfile, '-r', redux, '-o'], log, env=env, cwd=redux)
        if rc != 0:
            raise StageError('reduce failed', f'run_pypeit exit {rc}; see {log}')

        # 5. QA
        stage('qa')
        from pypeit.spectrographs.util import load_spectrograph
        platescale = load_spectrograph(SPECTROGRAPH).get_detector_par(1)['platescale']
        manifest['wave_qa'] = wave_qa(redux)
        manifest['objects'], missing = spec1d_qa(redux, tbl, platescale)
        for o in manifest['objects']:
            print(f"  {o['frame']} {o['target']:16s} {o['sign']:8s} spat {o['spat_pixpos']:7.1f} "
                  f"FWHM {o['fwhm_pix']:.2f} pix = {o['fwhm_arcsec']:.2f}\" S/N {o['s2n']:.1f}")
        for w in manifest['wave_qa']:
            print(f"  {w['file']} slit {w['slit']}: RMS {w['rms_pix']} pix "
                  f"(threshold {w.get('rms_thresh_pix')}) {'ok' if w['pass'] else 'FAIL'}")
        if missing:
            raise StageError('no trace', f'no spec1d objects for {missing}')

        # 6. sensfunc
        if args.sens:
            stage('sensfunc')
            sens_dir.mkdir(parents=True, exist_ok=True)
            stds = [o['spec1d'] for o in manifest['objects'] if 'standard' in o['frametype']]
            for spec1d in sorted(set(stds)):
                out = sens_dir / f'sens_{Path(spec1d).stem.replace("spec1d_", "")}.fits'
                rc = run(['pypeit_sensfunc', redux / 'Science' / spec1d, '-s', args.sens,
                          '-o', out], log, env=env, cwd=sens_dir)
                manifest['sensfuncs'].append({'spec1d': spec1d, 'sens': out.name, 'exit': rc})
                if rc != 0 or not out.exists():
                    raise StageError('sens failed', f'pypeit_sensfunc exit {rc} on {spec1d}')

        # 7. calibration monitor (design 4.9): flags only, never fails the night (D47)
        if args.monitor:
            stage('monitor')
            rc = run([sys.executable, REPO / 'scripts' / 'mosfire' / 'harvest_sens.py', 'monitor', date],
                     log, env=env)
            manifest['monitor'] = {'exit': rc, 'file': f'harvest/{date}_monitor.ecsv'}
            if rc != 0:
                print(f'WARNING: monitor exit {rc}; the night is not failed (D47)')
        return 0
    except StageError as exc:
        status = exc.status
        manifest['error'] = str(exc)
        print(f'ERROR [{status}]: {exc}', file=sys.stderr)
        return EXIT[status]
    except Exception as exc:  # noqa: BLE001 - classify by the stage that raised
        last = list(starts)[-1] if starts else 'start'
        status = {'pypeit_setup': 'setup failed', 'patch': 'setup failed',
                  'run_pypeit': 'reduce failed', 'qa': 'reduce failed',
                  'sensfunc': 'sens failed'}.get(last, 'setup failed')
        manifest['error'] = f'{type(exc).__name__} in stage {last}: {exc}'
        manifest['traceback'] = traceback.format_exc()
        print(manifest['traceback'], file=sys.stderr)
        print(f'ERROR [{status}]: {manifest["error"]}', file=sys.stderr)
        return EXIT[status]
    finally:
        # 7. manifest (always), then 8. push
        manifest['status'] = status
        for d in (redux / 'Science', redux / 'Calibrations', sens_dir):
            if d.exists():
                for f in sorted(d.glob('*.fits')):
                    manifest['product_sha256'][str(f.relative_to(night))] = sha256sum(f)
        manifest['qa_png'] = sorted(str(p.relative_to(night)) for p in (redux / 'QA').rglob('*.png')) \
            if (redux / 'QA').exists() else []
        manifest['finished'] = utcnow()
        if starts:
            last = list(starts)[-1]
            timings[last] = round(time.time() - starts[last], 1)
        timings['total'] = round(time.time() - t0, 1)
        (night / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=str) + '\n')
        print(f'Wrote {night / "run_manifest.json"} (status {status}, {timings["total"]:.0f} s)')
        if args.s3_push:
            rc = run([sys.executable, s3_sync, 'push', args.s3_push.strip('/')], log, env=env)
            if rc != 0 and status == 'success':
                print('ERROR [push failed]', file=sys.stderr)
                sys.exit(EXIT['push failed'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='S3 hooks: --s3-pull fetches <instrument>/<DATE>/raw from s3://$KECK_ETCS_BUCKET '
               'into the data root before setup; --s3-push PREFIX pushes $data_root/PREFIX (e.g. '
               'mosfire/20220409) after run_manifest.json is written. Both call '
               'scripts/nautilus/s3_sync.py (idempotent by key and size; credentials from '
               'AWS_PROFILE or AWS_*) and are no-ops when not given. Exit codes: '
               + ', '.join(f'{v} {k}' for k, v in EXIT.items()) + '.')
    parser.add_argument('date', help='Night, YYYYMMDD')
    parser.add_argument('--filter', help='Filter to reduce (default: the only one present)')
    parser.add_argument('--par', help='File with the PypeIt parameter block (default: built-in, '
                                      'from the dev-suite J2 template)')
    parser.add_argument('--sens', help='.sens file; run pypeit_sensfunc on each standard')
    parser.add_argument('--scratch', metavar='DIR', help='Use DIR as the data root for this run')
    parser.add_argument('--link-raw-from', metavar='DIR',
                        help='Symlink raw *.fits from DIR into the night (local alternative to --s3-pull)')
    parser.add_argument('--s3-pull', action='store_true', help='Pull raw frames from S3 first')
    parser.add_argument('--s3-push', metavar='PREFIX', help='Push $data_root/PREFIX to S3 at the end')
    parser.add_argument('--save-pypeit', metavar='FILE', help='Also save the patched PypeIt file '
                        '(raw path replaced by PATH_TO_RAW_DATA)')
    parser.add_argument('--setup-only', action='store_true', help='Stop after writing the PypeIt file')
    parser.add_argument('--monitor', action='store_true',
                        help='Run the calibration monitor at the end (harvest_sens.py monitor; never fails the night)')
    parser.add_argument('--skip-pin-check', action='store_true',
                        help='Run even if the pin check fails (recorded in run_manifest.json)')
    sys.exit(main(parser.parse_args()))
