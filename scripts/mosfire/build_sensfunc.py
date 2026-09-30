#!/usr/bin/env python
"""Build the J-band sensitivity function(s) for one MOSFIRE night's standard.

Usage:
    conda run -n pypeit14b python scripts/mosfire/build_sensfunc.py DATE
        [--standard NAME] [--sens FILE] [--frames-only]

e.g. ``build_sensfunc.py 20220409 --standard LDS749B``.

For the standard frames reduced by ``reduce_standard.py`` (their spec1d files
in ``<night>/redux/Science``, identified from ``<night>/run_manifest.json``):

1. ``pypeit_sensfunc`` on each frame's spec1d ->
   ``sens/sens_<NAME>_<DATE>_<frameno>.fits`` (per-frame zero points, used
   as a consistency check);
2. unless ``--frames-only``: ``pypeit_coadd_1dspec`` of all the standard
   frames in counts (``flux_value = False``) ->
   ``sens/spec1d_coadd_<NAME>_<DATE>.fits``, then ``pypeit_sensfunc`` on the
   coadd -> ``sens/sens_<NAME>_<DATE>.fits`` (the night's product).

The coadd is a weighted mean of counts and carries the first frame's header
(PypeIt coadd1d), so its ``EXPTIME`` is one frame's exposure time; that is
the right normalization for a mean of equal-length frames, and the script
refuses to coadd frames whose exposure times differ. ``AIRMASS`` is the
first frame's too (the log reports the spread).

``--sens`` defaults to ``keck_etcs/data/pypeit_par/keck_mosfire_J.sens``.
Each PypeIt call is logged to ``sens/<output stem>.log``.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SENS = REPO / 'keck_etcs' / 'data' / 'pypeit_par' / 'keck_mosfire_J.sens'


def run(cmd, log, cwd):
    print(f'$ {" ".join(str(c) for c in cmd)}  (log {log.name})', flush=True)
    with open(log, 'w') as f:
        rc = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT,
                            cwd=cwd).returncode
    if rc != 0:
        raise RuntimeError(f'{cmd[0]} failed (exit {rc}); see {log}')


def main(date, standard=None, sens=None, frames_only=False):
    night = paths.night_dir('mosfire', date)
    manifest = json.loads((night / 'run_manifest.json').read_text())
    sens = Path(sens) if sens else DEFAULT_SENS
    outdir = night / 'sens'
    outdir.mkdir(parents=True, exist_ok=True)

    objs = [o for o in manifest['objects'] if 'standard' in o['frametype']]
    if not objs:
        print(f'No standard objects in {night / "run_manifest.json"}')
        return 1
    frames = {f['filename']: f for f in manifest['frames']}
    name = standard or objs[0]['target']
    exptimes = sorted({frames[o['frame']]['exptime'] for o in objs})
    airmasses = [frames[o['frame']]['airmass'] for o in objs]
    print(f'{len(objs)} standard frame(s) of {name}: exptime {exptimes} s, '
          f'airmass {min(airmasses):.4f}-{max(airmasses):.4f}')

    # 1. per frame
    for o in objs:
        frameno = Path(o['frame']).stem.split('_')[-1]
        out = outdir / f'sens_{name}_{date}_{frameno}.fits'
        run(['pypeit_sensfunc', night / 'redux' / 'Science' / o['spec1d'], '-s', sens, '-o', out],
            out.with_suffix('.log'), outdir)

    if frames_only or len(objs) < 2:
        return 0
    if len(exptimes) != 1:
        print(f'Not coadding: exposure times differ ({exptimes})')
        return 1

    # 2. coadd in counts, then the night's sensfunc
    coadd = outdir / f'spec1d_coadd_{name}_{date}.fits'
    c1d = outdir / f'coadd_{name}_{date}.coadd1d'
    rows = '\n'.join(f'    {night / "redux" / "Science" / o["spec1d"]} | {o["name"]}' for o in objs)
    c1d.write_text(f"""# Written by scripts/mosfire/build_sensfunc.py
[rdx]
  spectrograph = keck_mosfire
[coadd1d]
  coaddfile = {coadd}
  flux_value = False

coadd1d read
    filename | obj_id
{rows}
coadd1d end
""")
    run(['pypeit_coadd_1dspec', c1d], coadd.with_suffix('.log'), outdir)
    out = outdir / f'sens_{name}_{date}.fits'
    run(['pypeit_sensfunc', coadd, '-s', sens, '-o', out], out.with_suffix('.log'), outdir)
    print(f'Wrote {out}')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('date', help='Night, YYYYMMDD')
    parser.add_argument('--standard', help='Standard name for the file names (default: TARGNAME)')
    parser.add_argument('--sens', help=f'.sens file (default {DEFAULT_SENS.relative_to(REPO)})')
    parser.add_argument('--frames-only', action='store_true', help='Skip the coadd')
    sys.exit(main(**vars(parser.parse_args())))
