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

A0V standards (design D2, N3; plan S15a): with ``--std-class A0V`` and
``--jmag`` (defaults: the night-manifest columns ``std_class`` and
``jmag_2mass``, which the night job exports as ``STD_CLASS`` and
``JMAG_2MASS``), the ``.sens`` file is copied to ``sens/<NAME>_<DATE>_A0V.sens``
with ``star_type = A0`` and ``star_mag = V_eq`` added under ``[sensfunc]``:
PypeIt's Vega model scaled to the star's 2MASS J
(``keck_etcs.calib.standards``). The model record is written to
``sens/<NAME>_<DATE>_std_model.json``. Archive standards (white dwarfs) need
nothing: PypeIt finds them by position.
"""
import argparse
import json
import os
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


def main(date, standard=None, sens=None, frames_only=False, std_class=None, jmag=None):
    night = paths.night_dir('mosfire', date)
    manifest = json.loads((night / 'run_manifest.json').read_text())
    sens = Path(sens) if sens else DEFAULT_SENS
    outdir = night / 'sens'
    outdir.mkdir(parents=True, exist_ok=True)
    std_class = std_class if std_class is not None else os.environ.get('STD_CLASS') or None
    jmag = jmag if jmag is not None else (float(os.environ['JMAG_2MASS']) if os.environ.get('JMAG_2MASS') else None)

    objs = [o for o in manifest['objects'] if 'standard' in o['frametype']]
    if manifest.get('specphot'):
        # long2pos_specphot (reduce_standard.py): only frames whose brightest object (the star)
        # is in a 4.0" bar measure the throughput; that object only
        use = [o for o in objs if o.get('specphot_use')]
        print(f'long2pos_specphot: {len(use)} of {len({o["frame"] for o in objs})} standard frame(s) '
              f'with the star in a 4.0" bar: {[o["frame"] for o in use]}')
        objs = use
    if not objs:
        print(f'No standard objects in {night / "run_manifest.json"}')
        return 1
    frames = {f['filename']: f for f in manifest['frames']}
    name = standard or objs[0]['target']
    exptimes = sorted({frames[o['frame']]['exptime'] for o in objs})
    airmasses = [frames[o['frame']]['airmass'] for o in objs]
    print(f'{len(objs)} standard frame(s) of {name}: exptime {exptimes} s, '
          f'airmass {min(airmasses):.4f}-{max(airmasses):.4f}')
    if std_class and str(std_class).upper().startswith('A0'):
        if jmag is None:
            print('A0V standard without a 2MASS J magnitude (--jmag or JMAG_2MASS)')
            return 1
        from keck_etcs.calib import standards
        text, rec = standards.write_sens_par(sens.read_text(), jmag)
        sens = outdir / f'{name}_{date}_A0V.sens'
        sens.write_text(text)
        rec.update({'standard': name, 'std_class': 'A0V', 'sens_par': sens.name})
        (outdir / f'{name}_{date}_std_model.json').write_text(json.dumps(rec, indent=1) + '\n')
        print(f"A0V model: 2MASS J {jmag} -> PypeIt Vega model at V_eq {rec['v_equivalent']} ({sens.name})")

    # 1. per frame
    for o in objs:
        frameno = Path(o['frame']).stem.split('_')[-1]
        out = outdir / f'sens_{name}_{date}_{frameno}.fits'
        run(['pypeit_sensfunc', night / 'redux' / 'Science' / o['spec1d'], '-s', sens, '-o', out],
            out.with_suffix('.log'), outdir)

    if frames_only:
        return 0
    if len(objs) < 2:
        import shutil
        frameno = Path(objs[0]['frame']).stem.split('_')[-1]
        shutil.copy(outdir / f'sens_{name}_{date}_{frameno}.fits', outdir / f'sens_{name}_{date}.fits')
        print(f'One frame: sens_{name}_{date}.fits is its per-frame sensfunc')
        return 0
    if len(exptimes) != 1:
        # coadd only equal-length frames (the coadd keeps one frame's EXPTIME): the exposure time
        # with the largest total integration (S15a pilot: 2014-06-01 has 11.6 s and 21.8 s frames)
        tot = {e: sum(frames[o['frame']]['exptime'] == e for o in objs) * e for e in exptimes}
        keep = max(tot, key=tot.get)
        objs = [o for o in objs if frames[o['frame']]['exptime'] == keep]
        print(f'Exposure times differ ({exptimes}): coadding the {len(objs)} frame(s) of {keep} s')
        if len(objs) < 2:
            import shutil
            frameno = Path(objs[0]['frame']).stem.split('_')[-1]
            shutil.copy(outdir / f'sens_{name}_{date}_{frameno}.fits', outdir / f'sens_{name}_{date}.fits')
            print(f'One frame: sens_{name}_{date}.fits is its per-frame sensfunc')
            return 0

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
    parser.add_argument('--std-class', help='archive (WD) or A0V (default: $STD_CLASS; archive if unset)')
    parser.add_argument('--jmag', type=float, help='2MASS J of an A0V standard (default: $JMAG_2MASS)')
    sys.exit(main(**vars(parser.parse_args())))
