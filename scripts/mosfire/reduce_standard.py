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
 5. Check that every standard frame has a spec1d with at least one object
    (else ``no trace``); a science frame without one is only recorded
    (``science_without_objects``), since a faint validation target may escape
    PypeIt's object finding; report FWHM, S/N and the wavelength RMS.
 6. ``--sens FILE``: ``pypeit_sensfunc`` on each standard spec1d into
    ``sens/sens_<spec1d stem>.fits``.
 7. Write ``<night>/run_manifest.json`` (design 4.8.5), on failure too.
 8. ``--s3-push PREFIX``: push ``$data_root/PREFIX`` to the bucket.

Frame typing. PypeIt's MOSFIRE rule keys on ``FLATSPEC``, which is 1 in
every frame of 2022-04-09 (science and standard included), so every frame
comes out as a flat. This driver types from the dome-lamp and telescope
cards instead:

- ``FLAMP1`` or ``FLAMP2 == 'on'`` -> ``pixelflat,illumflat,trace``; headers
  without FLAMP cards (e.g. 2013) use ``FLATSPEC == 1`` off sky instead;
- lamps off and ``TARGNAME`` contains "FLAT", or the telescope is parked
  (``AXESTAT`` neither ``tracking`` nor ``slewing``; nodded frames read
  ``slewing``) -> ``lampoffflats``;
- Ne or Ar lamp on (``PWSTATA7``/``PWSTATA8 == 1``, PypeIt's ``arclamp``)
  -> ``arc,tilt`` on ``long2pos_specphot`` nights (PypeIt's wavelength
  calibration for that mask); on other nights the lamp arcs are left out of
  the PypeIt file (they stay in ``raw/`` for the calibration monitor, design
  D44), since PypeIt calibrates long slits on the OH lines;
- on sky, at a spectrophotometric standard's position
  (``pypeit.core.standard.get_archive_standard(check=True)``) -> ``standard``,
  whatever the exposure time (PypeIt types standards by ``exptime < 20 s``);
- on sky within 60" of an A0V standard's position from the night manifest
  (``--std-class A0V --std-ra --std-dec``; plan S15a, design N3) ->
  ``standard``;
- other on-sky frames -> ``arc,science,tilt`` (OH lines as the arc).

When ``raw/manifest.ecsv`` exists (written by
``scripts/koa/download_mosfire_night.py``), only the frames it lists are used,
and its ``frame_type`` refines the typing:
``oh_arc`` frames (narrow-slit on-sky frames downloaded only for their OH
lines, often of faint unrelated targets) become ``arc,tilt``, so the night
does not fail ``no trace`` on them; ``standard`` frames are typed
``standard``.

Nod pairing. Long-slit nights pair A and B frames in time order (below).
``long2pos`` and ``long2pos_specphot`` masks use PypeIt's own
``keck_mosfire.get_comb_group`` (B-A pairs; for ``long2pos_specphot`` a
narrow-slit frame is the background of the wide-slit one).

long2pos_specphot (plan S15a pilot): each CSU bar is traced as its own slit
(``use_maskdesign = False``, :data:`SPECPHOT_SLITEDGES`), the 4.0" bars are
found from the mask's ``Mechanical_Slit_List`` (checked against the arc line
widths, :func:`specphot_wide_slits`), and only frames whose brightest
standard object lies in a 4.0" bar are used (``specphot_use``;
``run_manifest.json`` ``specphot``). ``no trace`` then means no such frame.

OH arcs: at most :data:`MAX_OH_ARCS` on-sky frames are typed as arcs (the
longest, then the nearest in time to the standard); further science frames
are typed ``science`` only (2025-07-23: 36 frames combined into the arc ran
out of 16 GiB).

The standard (``--std-class``, ``--std-name``, ``--std-ra``, ``--std-dec``,
``--jmag``; defaults from the night-manifest columns the night job exports,
``STD_CLASS``, ``STANDARD``, ``STD_RA``, ``STD_DEC``, ``JMAG_2MASS``) is
recorded in ``run_manifest.json`` under ``standard``; the A0V sensfunc
itself is built by ``build_sensfunc.py``. The manifest's optional ``filter``
column (``$FILTER``) is the default ``--filter``, for nights with the standard
in more than one band (plan S14).

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

# OH arcs (S15a pilot, 2026-10-06): 2025-07-23 has 36 on-sky science frames; typed as arcs, PypeIt
# combined all 36 into the arc image and the pod was OOM-killed at 16 GiB (2022-04-09: 16 frames,
# 6 GiB peak). At most MAX_OH_ARCS frames serve as arc/tilt (the longest, then the nearest in time
# to the standard); the other science frames are typed science only.
MAX_OH_ARCS = 16

# long2pos_specphot (plan S15a pilot, 2026-10-06): positions A and C are each three CSU bars,
# 0.7" | 4.0" | 0.7" wide (the raw frames' Mechanical_Slit_List), and posB is one 4.0" bar.
# PypeIt's mask-design matching merges or drops these bars (2017-06-15: one slit kept, two bars of
# posC; posA lost; 2024-07-21: the one slit kept fully masked), so the 4.0" bar that holds the star
# is not reduced. Each bar is traced as its own slit instead; the 4.0" bars are the
# spectrophotometric slits.
SPECPHOT_SLITEDGES = ['use_maskdesign = False']
# wavelength RMS limit for using a 4.0" bar (as nautilus/gates.py; flat-topped arc lines, so an
# absolute limit: 0.5 pix = 0.8 A, negligible for a throughput curve)
SPECPHOT_RMS_PIX = 0.5


def with_slitedges(par_text, lines):
    """Add ``lines`` to the ``[[slitedges]]`` block of a parameter block (created if absent)."""
    out = par_text.rstrip('\n').splitlines()
    add = [f'    {ln}' for ln in lines]
    for i, ln in enumerate(out):
        if ln.strip() == '[[slitedges]]':
            return '\n'.join(out[:i + 1] + add + out[i + 1:]) + '\n'
    for i, ln in enumerate(out):
        if ln.strip() == '[calibrations]':
            return '\n'.join(out[:i + 1] + ['  [[slitedges]]'] + add + out[i + 1:]) + '\n'
    return '\n'.join(['[calibrations]', '  [[slitedges]]'] + add + out) + '\n'


def split_merged_bars(pfile, redux, raw_file, log, env):
    """Trace a long2pos_specphot night's slit edges once and split slits that hold several bars.

    On some nights the flats show no gap between the three bars of a position
    (2015-09-04: three slits, 127 pixels wide, for seven bars), so PypeIt
    traces one slit per position and the 4.0" bar cannot be told apart. This
    runs ``pypeit_trace_edges`` on ``pfile``; if it finds fewer slits than the
    mask has bars (``Mechanical_Slit_List``), every slit wider than one bar is
    replaced, through PypeIt's ``rm_slits``/``add_slits`` (removed first, then
    added), by ``k`` equal bars, ``k`` = the slit width plus one bar gap over
    the CSU pitch (bar length plus gap, from the mask's plate scale). The two
    lines are written into the ``[[slitedges]]`` block of ``pfile``. Returns a
    record for ``run_manifest.json`` (``None`` when nothing is changed).
    """
    from pypeit.slittrace import SlitTraceSet
    from pypeit.spectrographs.keck_mosfire import KeckMOSFIRESpectrograph as K
    work = Path(redux) / 'edge_check'
    rc = run(['pypeit_trace_edges', '-f', pfile, '-p', work, '-o', '--log_file', 'None'], log, env=env, cwd=redux)
    files = sorted((work / 'Calibrations').glob('Slits_*'))
    if rc != 0 or not files:
        return {'action': 'none', 'reason': f'pypeit_trace_edges exit {rc}'}
    slits = SlitTraceSet.from_file(files[0])
    left, right, _ = slits.select_edges()
    with fits.open(raw_file) as hdul:
        nbars = sum(1 for r in hdul['Mechanical_Slit_List'].data if str(r['Slit_Number']).strip())
        ps = hdul[0].header['PSCALE']
    shutil.rmtree(work, ignore_errors=True)
    row = left.shape[0] // 2
    edges = sorted((float(left[row, i]), float(right[row, i])) for i in range(slits.nslits))
    rec = {'traced': [[round(a, 1), round(b, 1)] for a, b in edges], 'nbars': nbars, 'row': row}
    if len(edges) >= nbars:
        return dict(rec, action='none', reason=f'{len(edges)} slits for {nbars} bars')
    gap = K._slit_gap(ps)
    pitch = K._CSUlength(ps) + gap
    rm, add, n = [], [], 0
    for a, b in edges:
        k = max(1, int(round((b - a + gap) / pitch)))
        n += k
        if k == 1:
            continue
        rm.append(f'1:{row}:{0.5 * (a + b):.0f}')
        step = (b - a + gap) / k
        add += [f'1:{row}:{a + i * step:.0f}:{a + i * step + step - gap:.0f}' for i in range(k)]
    if n != nbars or not rm:
        return dict(rec, action='none', reason=f'split gives {n} slits for {nbars} bars')
    text = Path(pfile).read_text()
    block = f"    rm_slits = {'; '.join(rm)}\n    add_slits = {'; '.join(add)}\n"
    assert text.count('  [[slitedges]]\n') == 1
    Path(pfile).write_text(text.replace('  [[slitedges]]\n', '  [[slitedges]]\n' + block, 1))
    return dict(rec, action='split', rm_slits=rm, add_slits=add)


def specphot_wide_slits(raw_file, wave_rows):
    """The 4.0" bars of a long2pos_specphot reduction (``spat_id`` of the traced slits).

    Geometry: the mask's ``Mechanical_Slit_List`` (bar widths by slit number); the
    traced slits in increasing spatial position are the bars in decreasing slit
    number (2017-06-15: 26, 25, ..., 20). Used when the counts agree. The arc
    line FWHM per slit (WaveCalib) is the check: a 4.0" bar's arc lines are
    wider than a 0.7" bar's (2017-06-15: 3.0-3.8 against 1.8-2.1 pix). Without
    the geometry, the bars whose arc FWHM is above the midpoint of the range are
    taken, when the range spans more than a factor 1.3.
    """
    fw = {int(w['slit']): w.get('fwhm_pix') for w in wave_rows}
    slits = sorted(fw)
    rec = {'slits': slits, 'arc_fwhm_pix': fw, 'bars': None, 'method': None, 'wide': [],
           'fwhm_check': None}
    bars = []
    try:
        with fits.open(raw_file) as hdul:
            mech = hdul['Mechanical_Slit_List'].data
            bars = sorted(((int(str(r['Slit_Number']).strip()), float(str(r['Slit_width']).strip()))
                           for r in mech if str(r['Slit_Number']).strip()), reverse=True)
    except (KeyError, ValueError, OSError):
        bars = []
    good = [f for f in fw.values() if f is not None]
    if bars and len(bars) == len(slits):
        rec['bars'] = [{'spat_id': s, 'bar': b, 'width_arcsec': w} for s, (b, w) in zip(slits, bars)]
        rec['wide'] = [s for s, (_, w) in zip(slits, bars) if w > 2.0]
        rec['method'] = 'geometry'
        narrow = [fw[s] for s in slits if s not in rec['wide'] and fw[s] is not None]
        wide = [fw[s] for s in rec['wide'] if fw[s] is not None]
        if narrow and wide:
            rec['fwhm_check'] = bool(min(wide) > max(narrow))
    elif len(good) >= 2 and max(good) > 1.3 * min(good):
        mid = 0.5 * (max(good) + min(good))
        rec['wide'] = [s for s in slits if fw[s] is not None and fw[s] > mid]
        rec['method'] = 'arc_fwhm'
    return rec


def cap_oh_arcs(tbl, nmax=MAX_OH_ARCS):
    """Keep at most ``nmax`` on-sky frames as OH arcs; return notes (see :data:`MAX_OH_ARCS`)."""
    oh = [i for i, t in enumerate(tbl['frametype']) if t in ('arc,science,tilt', 'arc,tilt')]
    if len(oh) <= nmax:
        return []
    std = [float(m) for m, t in zip(tbl['mjd'], tbl['frametype']) if 'standard' in t]
    t0 = float(np.median(std)) if std else float(np.median(tbl['mjd']))
    order = sorted(oh, key=lambda i: (-float(tbl['exptime'][i]), abs(float(tbl['mjd'][i]) - t0)))
    keep, drop = set(order[:nmax]), order[nmax:]
    dropped = []
    for i in drop:
        tbl['frametype'][i] = 'science' if tbl['frametype'][i] == 'arc,science,tilt' else 'DROP'
        dropped.append(str(tbl['filename'][i]))
    return [f'{len(oh)} OH-arc frames: the {nmax} longest (nearest the standard) kept as arc/tilt; '
            f'{len(drop)} retyped science only, or left out if downloaded only for OH: {dropped}']


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

LAMP_ARC = 'lamp_arc'
"""Internal type of a Ne/Ar lamp frame before :func:`build_pypeit_file` decides its use."""


def separation_arcsec(ra1, dec1, ra2, dec2):
    """Angular separation [arcsec] of two positions given in degrees."""
    r1, d1, r2, d2 = np.radians([ra1, dec1, ra2, dec2])
    h = np.sin((d2 - d1) / 2) ** 2 + np.cos(d1) * np.cos(d2) * np.sin((r2 - r1) / 2) ** 2
    return float(np.degrees(2 * np.arcsin(np.sqrt(min(h, 1.0)))) * 3600.0)


def classify(hdr, ra, dec, std=None):
    """Frame type from the lamp and telescope cards (see module docstring).

    ``ra``, ``dec`` (deg) are PypeIt's metadata values for the frame; ``std``
    is the night's standard record (``std_class``, ``ra``, ``dec``).
    """
    from pypeit.core import standard
    from keck_etcs.calib.standards import A0V_MATCH_ARCSEC
    on_sky = str(hdr.get('AXESTAT', '')).strip().lower() in ('tracking', 'slewing')
    if 'FLAMP1' in hdr or 'FLAMP2' in hdr:
        lamp_on = any(str(hdr.get(k, '')).strip().lower() == 'on' for k in ('FLAMP1', 'FLAMP2'))
    else:
        # older headers (e.g. 2013) have no FLAMP cards; FLATSPEC is then reliable off sky
        lamp_on = (not on_sky) and hdr.get('FLATSPEC') == 1
    if lamp_on:
        return 'pixelflat,illumflat,trace'
    if hdr.get('PWSTATA7') == 1 or hdr.get('PWSTATA8') == 1:
        return LAMP_ARC
    if not on_sky or 'FLAT' in str(hdr.get('TARGNAME', '')).upper():
        return 'lampoffflats'
    if standard.get_archive_standard(float(ra), float(dec), check=True):
        return 'standard'
    if std and std.get('std_class') == 'A0V' and std.get('ra') is not None and std.get('dec') is not None \
            and separation_arcsec(float(ra), float(dec), std['ra'], std['dec']) <= A0V_MATCH_ARCSEC:
        return 'standard'
    return 'arc,science,tilt'


def raw_manifest_types(raw_dir):
    """``{file: frame_type}`` from ``raw/manifest.ecsv`` (KOA downloads), or {} without one."""
    p = Path(raw_dir) / 'manifest.ecsv'
    if not p.exists():
        return {}
    t = Table.read(p, format='ascii.ecsv')
    return {str(f): str(k) for f, k in zip(t['file'], t['frame_type'])}


def pair_long2pos(tbl):
    """``comb_id``/``bkg_id`` for long2pos masks from PypeIt's ``get_comb_group``; return notes."""
    from pypeit.spectrographs.util import load_spectrograph
    onsky = np.array([('science' in t) or ('standard' in t) for t in tbl['frametype']])
    tbl['comb_id'] = -1
    tbl['bkg_id'] = -1
    for n, i in enumerate(np.where(onsky)[0]):
        tbl['comb_id'][i] = n + 1
    tbl['setup'] = 'A'
    load_spectrograph(SPECTROGRAPH).get_comb_group(tbl)
    tbl.remove_column('setup')
    return [f'{tbl["filename"][i]}: no background frame (PypeIt long2pos pairing)'
            for i in np.where(onsky)[0] if tbl['bkg_id'][i] == -1]


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


def build_pypeit_file(setup_dir, out_file, filt, par_text, raw_dir, std=None):
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
    # pypeit_setup lists calibration frames shared by several setups in each of them: keep one row per file
    _, first = np.unique(np.asarray(tbl['filename']), return_index=True)
    n_dup = len(tbl) - len(first)
    tbl = tbl[np.sort(first)]
    filters = sorted(set(tbl['filter1']))
    if filt is None:
        if len(filters) != 1:
            raise StageError('setup failed', f'several filters {filters}; choose one with --filter')
        filt = filters[0]
    tbl = tbl[tbl['filter1'] == filt]
    if len(tbl) == 0:
        raise StageError('setup failed', f'no frames with filter {filt} (have {filters})')

    notes = [f'{n_dup} duplicate row(s) of frames listed in several pypeit_setup setups removed'] if n_dup else []
    old = list(tbl['frametype'])
    tbl['frametype'] = [classify(fits.getheader(Path(raw_dir) / fn), ra, dec, std)
                        for fn, ra, dec in zip(tbl['filename'], tbl['ra'], tbl['dec'])]
    koa = raw_manifest_types(raw_dir)
    if koa:
        # a KOA-downloaded night: use only the frames its raw/manifest.ecsv lists (a frame left in
        # raw/ by an earlier selection, e.g. an imaging-mode acquisition, is ignored)
        listed = np.array([str(fn) in koa for fn in tbl['filename']])
        if not listed.all():
            notes.append(f'{int((~listed).sum())} raw frame(s) not in raw/manifest.ecsv ignored: '
                         f'{list(tbl["filename"][~listed])}')
            old = [o for o, k in zip(old, listed) if k]
            tbl = tbl[listed]
    for i, fn in enumerate(tbl['filename']):
        kt = koa.get(str(fn))
        if kt == 'oh_arc' and tbl['frametype'][i] == 'arc,science,tilt':
            tbl['frametype'][i] = 'arc,tilt'
        elif kt == 'standard' and tbl['frametype'][i] == 'arc,science,tilt':
            tbl['frametype'][i] = 'standard'
    specphot = any('long2pos_specphot' in str(d) for d in tbl['decker'])
    long2pos = any('long2pos' in str(d) for d in tbl['decker'])
    lamp = np.array([t == LAMP_ARC for t in tbl['frametype']])
    if lamp.any():
        if specphot:
            tbl['frametype'][lamp] = 'arc,tilt'
            notes.append(f'{int(lamp.sum())} Ne/Ar lamp frame(s) typed arc,tilt (long2pos_specphot)')
        else:
            notes.append(f'{int(lamp.sum())} Ne/Ar lamp frame(s) left out of the PypeIt file '
                         f'(long slit: OH arcs; kept in raw/ for the monitor): {list(tbl["filename"][lamp])}')
            old = [o for o, k in zip(old, lamp) if not k]
            tbl = tbl[~lamp]
    if not specphot:
        notes += cap_oh_arcs(tbl)
        keep_rows = np.array([t != 'DROP' for t in tbl['frametype']])
        old = [o for o, k in zip(old, keep_rows) if k]
        tbl = tbl[keep_rows]
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
    if long2pos:
        notes += pair_long2pos(tbl)
        notes.append('long2pos mask: nod pairing from PypeIt keck_mosfire.get_comb_group')
    else:
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
                         'name': so['NAME'], 'slit': int(so['SLITID']),
                         'spat_pixpos': float(so['SPAT_PIXPOS']),
                         'fwhm_pix': fwhm,
                         'fwhm_arcsec': None if fwhm is None else fwhm * platescale,
                         's2n': None if so['S2N'] is None else float(so['S2N']),
                         'sign': 'positive' if np.nanmedian(so['OPT_COUNTS'] if so['OPT_COUNTS'] is not None
                                                            else so['BOX_COUNTS']) > 0 else 'negative'})
    return rows, missing


# ---------------------------------------------------------------- standard

def standard_record(args):
    """The night's standard from the options or the night-manifest environment (see docstring)."""
    from keck_etcs.calib import standards
    env = lambda k: os.environ.get(k) or None
    fl = lambda v: None if v in (None, '') else float(v)
    rec = {'name': args.std_name or env('STANDARD'), 'ra': fl(args.std_ra or env('STD_RA')),
           'dec': fl(args.std_dec or env('STD_DEC')), 'jmag_2mass': fl(args.jmag or env('JMAG_2MASS')),
           'std_class_manifest': args.std_class or env('STD_CLASS')}
    rec.update(standards.classify(rec['ra'], rec['dec'], std_class=rec['std_class_manifest']))
    if rec['std_class'] == 'A0V':
        if rec['ra'] is None or rec['dec'] is None:
            raise StageError('setup failed', 'A0V standard without STD_RA/STD_DEC: cannot identify its frames')
        if rec['jmag_2mass'] is None:
            raise StageError('setup failed', 'A0V standard without a 2MASS J (JMAG_2MASS)')
    return rec


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
        'standard': None,
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
        koa_types = raw_manifest_types(raw)
        specphot = any('long2pos_specphot' in str(fits.getheader(f).get('MASKNAME', '')) for f in frames
                       if koa_types.get(f.name, 'standard') == 'standard')
        if specphot and 'use_maskdesign' not in par_text:
            par_text = with_slitedges(par_text, SPECPHOT_SLITEDGES)
        manifest['par_block'] = par_text
        pfile = redux / f'{SPECTROGRAPH}_{date}.pypeit'
        std = standard_record(args)
        manifest['standard'] = std
        pfile, tbl, notes, filt = build_pypeit_file(setup_dir, pfile, args.filter, par_text, raw, std)
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

        if specphot:
            # long2pos_specphot: one slit per CSU bar, even when the flats show no bar gaps
            stage('bar_split')
            std_raw = [r['filename'] for r in tbl if 'standard' in r['frametype']]
            manifest['specphot_bar_split'] = split_merged_bars(pfile, redux, raw / std_raw[0], log, env)
            print(f"  long2pos_specphot bar split: {manifest['specphot_bar_split']}")
            manifest['pypeit_file_text'] = pfile.read_text()

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
        # only the standard must yield an object; a faint science (validation) target may not
        # be found by PypeIt's object finding, which must not cost the night its sensfunc
        std_files = {str(r['filename']) for r in tbl if 'standard' in r['frametype']}
        miss_std = [m for m in missing if m in std_files]
        miss_sci = [m for m in missing if m not in std_files]
        if miss_sci:
            manifest['science_without_objects'] = miss_sci
            print(f'  WARNING: no spec1d object in science frame(s) {miss_sci} (spec2d kept for validation)')
        if specphot:
            # the dither moves the star between the bars: only frames with the star in a 4.0" bar
            # measure the throughput (2017: YOFFSET 0; 2014 align mask: YOFFSET +-14)
            sp = specphot_wide_slits(raw / sorted(std_files)[0], manifest['wave_qa'])
            for o in manifest['objects']:
                o['wide_slit'] = o['slit'] in sp['wide']
            # a frame counts when its brightest object is in a 4.0" bar (2017-06-15: the B frames have
            # the star in a 0.7" bar and a faint nod residual, S/N 11-15, in the 4.0" bar). Objects
            # whose FWHM is outside 0.5-2x the night's median are sky-subtraction artefacts, not the
            # star (2014-06-01 frame 0357: seven objects, the brightest 12 pix wide in a 4.0" bar)
            # and are not candidates. A 4.0" bar counts only with a wavelength solution within
            # SPECPHOT_RMS_PIX (the posB bar has no 0.7" neighbors to calibrate it from).
            cand = [o for o in manifest['objects'] if 'standard' in o['frametype'] and o['sign'] == 'positive'
                    and o['fwhm_pix'] is not None]
            med = float(np.median([o['fwhm_pix'] for o in cand])) if cand else None
            rms = {w['slit']: w['rms_pix'] for w in manifest['wave_qa']}
            best = {}
            for o in cand:
                if not (0.5 * med <= o['fwhm_pix'] <= 2.0 * med):
                    continue
                if o['frame'] not in best or (o['s2n'] or 0) > (best[o['frame']]['s2n'] or 0):
                    best[o['frame']] = o
            for o in manifest['objects']:
                o['specphot_use'] = bool(o['wide_slit'] and best.get(o['frame']) is o
                                         and rms.get(o['slit']) is not None
                                         and rms[o['slit']] < SPECPHOT_RMS_PIX)
            wide_frames = sorted(o['frame'] for o in manifest['objects'] if o['specphot_use'])
            sp['standard_frames_wide'] = wide_frames
            sp['fwhm_median_pix'] = med
            sp['standard_frames_without_objects'] = miss_std
            manifest['specphot'] = sp
            print(f"  long2pos_specphot: 4.0\" bars {sp['wide']} ({sp['method']}; arc FWHM check "
                  f"{sp['fwhm_check']}); standard frames with the star in a 4.0\" bar: {wide_frames}")
            if miss_std:
                print(f'  WARNING: no spec1d object in standard frame(s) {miss_std} (not used for the sensfunc)')
            if not wide_frames:
                raise StageError('no trace', 'long2pos_specphot: no standard object in a 4.0" bar '
                                 f'(wide bars {sp["wide"]}, method {sp["method"]})')
        elif miss_std:
            raise StageError('no trace', f'no spec1d objects for standard frame(s) {miss_std}')

        # 6. sensfunc
        if args.sens:
            stage('sensfunc')
            sens_dir.mkdir(parents=True, exist_ok=True)
            stds = [o['spec1d'] for o in manifest['objects'] if 'standard' in o['frametype']
                    and o.get('specphot_use', True)]
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
    parser.add_argument('--filter', default=os.environ.get('FILTER') or None,
                        help='Filter to reduce (default: $FILTER from the night manifest, else the only one present)')
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
    parser.add_argument('--std-class', help='Standard class: archive (WD) or A0V (default: $STD_CLASS)')
    parser.add_argument('--std-name', help='Standard name (default: $STANDARD)')
    parser.add_argument('--std-ra', help='Standard RA [deg] (default: $STD_RA; needed for A0V)')
    parser.add_argument('--std-dec', help='Standard Dec [deg] (default: $STD_DEC; needed for A0V)')
    parser.add_argument('--jmag', help='2MASS J of an A0V standard (default: $JMAG_2MASS)')
    parser.add_argument('--skip-pin-check', action='store_true',
                        help='Run even if the pin check fails (recorded in run_manifest.json)')
    sys.exit(main(parser.parse_args()))
