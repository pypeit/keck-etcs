#!/usr/bin/env python
"""Is PypeIt's extraction of a nod pair stable under tiny input changes? (S4b investigation)

Usage:
    conda run -n pypeit14b python scripts/mosfire/extraction_stability_test.py DATE
        [--frames 0036 0037] [--eps 1e-6] [--n 6 | --ks K ...] [--jobs 3] [--outdir DIR]
        [--fixed-trace]

For realization k = 0..n-1, in ``DIR/r<k>/``:
- ``raw/``: symlinks to the night's calibration and standard frames, plus
  copies of the pair's science frames multiplied by ``1 + eps * N(0, 1)``
  (seed k; realization 0 is unperturbed). The standard must stay: PypeIt
  uses its trace as the tracing crutch for the science objects, and without
  it the global sky and the extraction differ;
- ``redux/Calibrations/``: a copy of the night's calibrations, which
  ``run_pypeit`` reuses, so only the science frames are processed;
- the committed PypeIt file
  (``scripts/mosfire/pypeit_files/keck_mosfire_<DATE>_J2.pypeit``), cut to the
  calibration frames and the pair; then ``run_pypeit``.

Then, per frame and realization: FWHM, S2N, median OPT and BOX counts
(1.17-1.24 um), and the number of ``EXTRACT``-flagged pixels within ±8
pixels of the trace (from the spec2d ``BPMMASK``). These show whether the
extraction has more than one outcome and how they differ. Results go to
``DIR/summary.ecsv``.

``--fixed-trace`` runs ``scripts/mosfire/run_pypeit_fixed_trace.py``
instead of ``run_pypeit``. That is an experiment only: it keeps the
object-finding trace through ``local_skysub_extract``, whose trace refinement
can walk off the object.
"""
import argparse
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[2]
WINDOW = (11700.0, 12400.0)


def prepare(night, date, frames, eps, k, wdir, no_refine_trace=False):
    raw = wdir / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    pfile_src = REPO / 'scripts' / 'mosfire' / 'pypeit_files' / f'keck_mosfire_{date}_J2.pypeit'
    lines, keep = [], []
    for line in pfile_src.read_text().splitlines():
        s = line.strip()
        if s.startswith('m') and '.fits' in s.split('|')[0]:
            fn = s.split('|')[0].strip()
            ftype = s.split('|')[1].strip()
            is_pair = any(f'_{f}.fits' in fn for f in frames)
            # the standard stays in: PypeIt uses its trace as the tracing crutch
            # for science objects of the same calibration group
            if 'flat' in ftype or 'standard' in ftype or is_pair:
                keep.append((fn, is_pair))
                lines.append(line)
            continue
        lines.append(line.replace('PATH_TO_RAW_DATA', str(raw)))
        if no_refine_trace and s == '[reduce]':
            # PypeIt ExtractionPar.refine_trace (etc-fixes): keep the object-finding trace
            lines += ['  [[extraction]]', '    refine_trace = False']
    for fn, is_pair in keep:
        src = (night / 'raw' / fn).resolve()
        dst = raw / fn
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        if is_pair:
            with fits.open(src) as h:
                if eps > 0 and k > 0:
                    rng = np.random.default_rng(k)
                    d = h[0].data
                    h[0].data = (d * (1 + eps * rng.standard_normal(d.shape))).astype(d.dtype)
                h.writeto(dst)
        else:
            dst.symlink_to(src)
    calib = wdir / 'redux' / 'Calibrations'
    if not calib.exists():
        shutil.copytree(night / 'redux' / 'Calibrations', calib)
    pf = wdir / 'redux' / f'pair_{date}.pypeit'
    pf.write_text('\n'.join(lines) + '\n')
    return pf


def reduce(pf, wdir, fixed_trace=False):
    log = wdir / 'run_pypeit.log'
    cmd = ([sys.executable, str(REPO / 'scripts' / 'mosfire' / 'run_pypeit_fixed_trace.py')]
           if fixed_trace else ['run_pypeit'])
    with open(log, 'w') as f:
        rc = subprocess.run(cmd + [str(pf), '-r', str(wdir / 'redux')], stdout=f,
                            stderr=subprocess.STDOUT, cwd=wdir / 'redux').returncode
    return rc


def measure(wdir, frames, k):
    from pypeit.specobjs import SpecObjs
    from pypeit.images.imagebitmask import ImageBitMask
    bm = ImageBitMask()
    rows = []
    for fr in frames:
        s1 = sorted((wdir / 'redux' / 'Science').glob(f'spec1d_*_{fr}-*.fits'))
        s2 = sorted((wdir / 'redux' / 'Science').glob(f'spec2d_*_{fr}-*.fits'))
        if not s1:
            rows.append({'k': k, 'frame': fr, 'ok': False})
            continue
        o = SpecObjs.from_fitsfile(str(s1[0]), chk_version=False)[0]
        sel = (o['OPT_WAVE'] > WINDOW[0]) & (o['OPT_WAVE'] < WINDOW[1])
        n_ext = -1
        if s2:
            mask = fits.getdata(s2[0], 'DET01-BPMMASK').astype(int)
            c = int(round(o['SPAT_PIXPOS']))
            n_ext = int(np.sum(bm.flagged(mask[:, c - 8:c + 9], flag='EXTRACT')))
        rows.append({'k': k, 'frame': fr, 'ok': True, 'spat': float(o['SPAT_PIXPOS']),
                     'fwhm': float(o['FWHM']), 's2n': float(o['S2N']),
                     'opt': float(np.median(o['OPT_COUNTS'][sel])),
                     'box': float(np.median(o['BOX_COUNTS'][sel])), 'n_extract_trace': n_ext})
    return rows


def one(args):
    night, date, frames, eps, k, outdir, fixed_trace, no_refine_trace = args
    wdir = outdir / f'r{k}'
    pf = prepare(night, date, frames, eps, k, wdir, no_refine_trace)
    rc = reduce(pf, wdir, fixed_trace)
    rows = measure(wdir, frames, k)
    for r in rows:
        r['rc'] = rc
    return rows


def main(date, frames=('0036', '0037'), eps=1e-6, n=6, jobs=3, outdir=None, ks=None,
         fixed_trace=False, no_refine_trace=False):
    night = paths.night_dir('mosfire', date)
    outdir = Path(outdir or night / 'extraction_stability').resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    tasks = [(night, date, list(frames), eps, k, outdir, fixed_trace, no_refine_trace)
             for k in (ks if ks else range(n))]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        rows = [r for rs in ex.map(one, tasks) for r in rs]
    tbl = Table(rows=rows)
    tbl.sort(['frame', 'k'])
    tbl.write(outdir / 'summary.ecsv', format='ascii.ecsv', overwrite=True)
    tbl.pprint(max_lines=-1, max_width=-1)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--frames', nargs='+', default=['0036', '0037'])
    p.add_argument('--eps', type=float, default=1e-6)
    p.add_argument('--n', type=int, default=6)
    p.add_argument('--jobs', type=int, default=3)
    p.add_argument('--outdir')
    p.add_argument('--ks', nargs='+', type=int, help='Explicit realization seeds (instead of 0..n-1)')
    p.add_argument('--fixed-trace', action='store_true',
                   help='EXPERIMENT: keep the object-finding trace during extraction')
    p.add_argument('--no-refine-trace', action='store_true',
                   help='Set PypeIt [reduce][[extraction]] refine_trace = False in the PypeIt file')
    a = p.parse_args()
    sys.exit(main(a.date, tuple(a.frames), a.eps, a.n, a.jobs, a.outdir, a.ks, a.fixed_trace,
                  a.no_refine_trace))
