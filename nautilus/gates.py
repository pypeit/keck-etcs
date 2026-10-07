#!/usr/bin/env python
"""Hard gates on one reduced night (design 4.8.7); exits non-zero on any failure.

Usage:
    python nautilus/gates.py DATE [--standard NAME] [--reference REF]
        [--json OUT] [--update-manifest]

Reads the night under ``$KECK_ETCS_DATA/mosfire/DATE`` (in a pod, the
scratch directory): ``run_manifest.json`` written by
``scripts/mosfire/reduce_standard.py`` and ``sens/sens_<NAME>_<DATE>.fits``
written by ``scripts/mosfire/build_sensfunc.py``.

Gates, every night:

1. ``spec1d``: every science and standard frame has a spec1d with at least
   one object, and the standard has frames at both nod positions (A and B),
   i.e. both traces;
2. ``wave_rms``: every slit's wavelength RMS is below PypeIt's threshold
   (``rms_thresh_frac_fwhm`` x the arc FWHM, from the manifest's ``wave_qa``);
3. ``zp_finite``: the zero point is finite over 1.117-1.260 um;
4. ``thru_median``: the median throughput over 1.117-1.260 um is 0.15-0.45.

With ``--reference REF`` (a local night-like directory, or
``s3://<bucket>/<prefix>``, which is pulled into ``$KECK_ETCS_DATA/<prefix>``):

5. ``ref_pin``: the reference's recorded ``pypeit_pin`` equals this run's
   PypeIt SHA and the reference's ``pin_check.pass`` is true. If not, the
   comparisons below are not made (FAIL). The reference's own
   ``pypeit_git_sha`` is expected to differ and is only reported (D35);
6. ``spec1d_agree``: reduction fidelity. For every frame, the median ratio
   of ``OPT_COUNTS`` (this run / reference) over 1.17-1.24 um is within
   0.1 percent;
7. ``zp_agree``: band-level zero-point agreement over 1.117-1.260 um. The
   throughput ratio 10**(0.4 dZP) must have its median within 2 percent of
   1 and its per-pixel 5-95 percentile range within 1 +- 0.05;
8. ``s2n_agree``: every object's ``S2N`` agrees with the reference's (matched
   by frame) to 5 percent.

The zero-point tolerances follow the S4b diagnosis (user decision,
2026-10-01). The IR telluric fit (``differential_evolution``, seed 777) is
deterministic for a given input, and the image and local stacks give
bit-identical fits on the same spec1d. But it is chaotic in its input:
perturbing the counts by 1e-5 moves the per-pixel zero point by up to
about 5 percent (5-95 percent range) and the band median by up to about 1
percent (``scripts/mosfire/sensfunc_perturbation_test.py``). A 1 percent
per-pixel gate would therefore test bitwise identity, not fidelity; the
spec1d gate tests fidelity directly.

``--update-manifest`` writes the results into ``run_manifest.json`` (key
``gates``) and adds the sha256 of the sens products. Exit status 0 when all
gates pass, 1 otherwise, 2 on missing inputs.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts' / 'mosfire'))
import inspect_sensfunc  # noqa: E402

from keck_etcs import paths, provenance  # noqa: E402

INSTRUMENT = 'mosfire'
THRU_RANGE = inspect_sensfunc.THRU_RANGE
ZP_MEDIAN_TOL = 0.02          # median pod/reference throughput ratio
ZP_PIXEL_TOL = 0.05           # its 5-95 percentile range
COUNTS_TOL = 0.001            # median OPT_COUNTS ratio per frame
COUNTS_WINDOW = (11700.0, 12400.0)
S2N_TOL = 0.05


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def gate(name, passed, detail):
    print(f'  [{"PASS" if passed else "FAIL"}] {name}: {detail}', flush=True)
    return {'name': name, 'pass': bool(passed), 'detail': detail}


def resolve_reference(ref):
    """Local directory of the reference, pulling it from S3 first if needed."""
    if not ref.startswith('s3://'):
        return Path(ref)
    bucket, _, prefix = ref[len('s3://'):].partition('/')
    prefix = prefix.strip('/')
    if bucket != paths.BUCKET:
        raise SystemExit(f'reference bucket {bucket} is not {paths.BUCKET}')
    rc = subprocess.run([sys.executable, str(REPO / 'scripts' / 'nautilus' / 's3_sync.py'),
                         'pull', prefix]).returncode
    if rc != 0:
        raise SystemExit(f's3_sync.py pull {prefix} failed (exit {rc})')
    return paths.data_root() / prefix


# wavelength RMS limit for the 4.0" bars of long2pos_specphot (see the wave_rms gate)
SPECPHOT_RMS_PIX = 0.5


def spec1d_agree(night, rdir, m):
    """Median OPT_COUNTS ratio per frame, this run / reference."""
    from pypeit.specobjs import SpecObjs
    rows, bad = [], []
    for o in m['objects']:
        mine = Path(night) / 'redux' / 'Science' / o['spec1d']
        ref = Path(rdir) / 'redux' / 'Science' / o['spec1d']
        if not (mine.exists() and ref.exists()):
            bad.append(f"{o['frame']} (missing {'reference' if mine.exists() else 'spec1d'})")
            continue
        a = SpecObjs.from_fitsfile(str(mine), chk_version=False)[0]
        b = SpecObjs.from_fitsfile(str(ref), chk_version=False)[0]
        sel = (a['OPT_WAVE'] > COUNTS_WINDOW[0]) & (a['OPT_WAVE'] < COUNTS_WINDOW[1])
        r = float(np.median(a['OPT_COUNTS'][sel]) /
                  np.median(np.interp(a['OPT_WAVE'][sel], b['OPT_WAVE'], b['OPT_COUNTS'])))
        rows.append(f"{o['frame']} {r:.6f}")
        if abs(r - 1) >= COUNTS_TOL:
            bad.append(o['frame'])
    return gate('spec1d_agree', not bad and bool(rows),
                'median OPT_COUNTS ratio ' + '; '.join(rows) + f' (tolerance {COUNTS_TOL})'
                + (f'; FAIL {bad}' if bad else ''))


def sens_file(night_dir, standard, date):
    return Path(night_dir) / 'sens' / f'sens_{standard}_{date}.fits'


def main(date, standard=None, reference=None, json_out=None, update_manifest=False):
    night = paths.night_dir(INSTRUMENT, date)
    mpath = night / 'run_manifest.json'
    if not mpath.exists():
        print(f'missing {mpath}')
        return 2
    m = json.loads(mpath.read_text())
    standard = standard or next((f['target'] for f in m['frames'] if 'standard' in f['frametype']),
                                None)
    sens = sens_file(night, standard, date)
    print(f'Gates for {night} (standard {standard}; sens {sens.name})', flush=True)
    results = []

    # 1. spec1d
    onsky = [f for f in m['frames'] if ('science' in f['frametype']) or ('standard' in f['frametype'])]
    with_obj = {o['frame'] for o in m['objects']}
    missing = [f['filename'] for f in onsky if f['filename'] not in with_obj]
    std = [f for f in onsky if 'standard' in f['frametype']]
    std_pos = sorted({str(f['dithpos']).strip() for f in std if f['filename'] in with_obj})
    n_sci = sum('science' in f['frametype'] and f['filename'] in with_obj for f in onsky)
    sp = m.get('specphot')
    if sp:
        # long2pos_specphot: the sensfunc needs the star in a 4.0" bar; frames with the star in a
        # 0.7" bar are not used, so a missing object there is reported only
        wide = sp.get('standard_frames_wide') or []
        ok = bool(wide)
        results.append(gate('spec1d', ok, f'long2pos_specphot: {len(wide)} standard frame(s) with the star in '
                            f'a 4.0" bar {wide}; {len(with_obj)}/{len(onsky)} on-sky frames with objects'
                            + (f' (missing {missing}, not used)' if missing else '')))
    else:
        ok = not missing and {'A', 'B'} <= set(std_pos)
        results.append(gate('spec1d', ok, f'{len(with_obj)}/{len(onsky)} on-sky frames with objects '
                            f'({n_sci} science, {len(std)} standard at nod positions {std_pos})'
                            + (f'; missing {missing}' if missing else '')))

    # 2. wavelength RMS
    wq = m.get('wave_qa') or []
    if sp:
        # long2pos_specphot: only the 4.0" bars that hold the standard in the sensfunc frames count.
        # Their arc lines are flat-topped (a 4" slit), so 0.11 x FWHM is not a meaningful centroid
        # limit; SPECPHOT_RMS_PIX bounds them instead (0.5 pix = 0.8 A, negligible for a throughput
        # curve; 2017-06-15: 0.13 and 0.27 pix)
        used = {o['slit'] for o in m['objects'] if o.get('specphot_use')}
        wq = [dict(w, rms_thresh_pix=SPECPHOT_RMS_PIX,
                   **{'pass': w['rms_pix'] is not None and w['rms_pix'] < SPECPHOT_RMS_PIX})
              for w in wq if w['slit'] in used]
    ok = bool(wq) and all(w['pass'] for w in wq)
    results.append(gate('wave_rms', ok, '; '.join(
        f"slit {w['slit']} RMS {w['rms_pix']:.3f} < {w['rms_thresh_pix']:.3f} pix" if w['rms_pix'] is not None
        else f"slit {w['slit']} no fit" for w in wq) or 'no WaveCalib'))

    # 3-4. sensfunc
    if not sens.exists():
        results.append(gate('zp_finite', False, f'missing {sens}'))
        results.append(gate('thru_median', False, f'missing {sens}'))
        pod = None
    else:
        pod, _ = inspect_sensfunc.inspect(sens)
        results.append(gate('zp_finite', pod['zp_finite_in_window'],
                            f"zero point finite over {pod['zp_range_A']} A"))
        t = pod['thru_median_window']
        results.append(gate('thru_median', t is not None and THRU_RANGE[0] <= t <= THRU_RANGE[1],
                            f'median throughput 1.117-1.260 um = {t:.4f} (allowed {THRU_RANGE})'))

    # 5-7. reference
    ref_info = None
    if reference:
        rdir = resolve_reference(reference)
        rm = json.loads((rdir / 'run_manifest.json').read_text())
        my_sha = provenance.git_shas()['pypeit']
        ref_pin = rm.get('pypeit_pin')
        ref_pass = bool((rm.get('pin_check') or {}).get('pass'))
        ok = ref_pin == my_sha and ref_pass
        ref_info = {'reference': reference, 'ref_pypeit_pin': ref_pin, 'ref_pin_check_pass': ref_pass,
                    'ref_pypeit_git_sha': rm.get('pypeit_git_sha'), 'pod_pypeit_sha': my_sha}
        results.append(gate('ref_pin', ok, f"reference pin {ref_pin} (pin_check.pass={ref_pass}) vs "
                            f"this run's PypeIt {my_sha}; reference ran at {rm.get('pypeit_git_sha')}"))
        if not ok:
            for name in ('spec1d_agree', 'zp_agree', 's2n_agree'):
                results.append(gate(name, False, 'not compared: reference pin mismatch'))
        else:
            results.append(spec1d_agree(night, rdir, m))
            rsens = sens_file(rdir, standard, date)
            if pod is None or not rsens.exists():
                results.append(gate('zp_agree', False, f'missing {sens if pod is None else rsens}'))
            else:
                a = inspect_sensfunc.load(sens)
                b = inspect_sensfunc.load(rsens)
                c = inspect_sensfunc.compare(a, b)
                ok = (abs(c['median_ratio'] - 1) < ZP_MEDIAN_TOL and abs(c['p05'] - 1) < ZP_PIXEL_TOL
                      and abs(c['p95'] - 1) < ZP_PIXEL_TOL)
                results.append(gate('zp_agree', ok,
                                    f"pod/reference throughput ratio: median {c['median_ratio']:.5f} "
                                    f"(tolerance {ZP_MEDIAN_TOL}), 5-95% {c['p05']:.5f}-{c['p95']:.5f} "
                                    f"(tolerance {ZP_PIXEL_TOL}), max |dev| {c['max_abs_dev']:.5f}"))
                ref_info['zp_comparison'] = c
            robj = {o['frame']: o for o in rm.get('objects', [])}
            rows, bad = [], []
            for o in m['objects']:
                r = robj.get(o['frame'])
                if r is None or not r.get('s2n') or o.get('s2n') is None:
                    bad.append(f"{o['frame']} (no reference)")
                    continue
                q = o['s2n'] / r['s2n'] - 1
                rows.append(f"{o['frame']} {o['s2n']:.2f}/{r['s2n']:.2f} ({100 * q:+.2f}%)")
                if abs(q) >= S2N_TOL:
                    bad.append(o['frame'])
            results.append(gate('s2n_agree', not bad and bool(rows),
                                '; '.join(rows) + (f'; FAIL {bad}' if bad else '')))

    passed = all(r['pass'] for r in results)
    summary = {'pass': passed, 'gates': results, 'reference': ref_info,
               'failed': [r['name'] for r in results if not r['pass']]}
    print(f"GATES: {'PASS' if passed else 'FAIL ' + ', '.join(summary['failed'])}", flush=True)
    if json_out:
        Path(json_out).write_text(json.dumps(summary, indent=2, default=str) + '\n')
    if update_manifest:
        m['gates'] = summary
        for f in sorted((night / 'sens').glob('*.fits')) if (night / 'sens').exists() else []:
            m.setdefault('product_sha256', {})[str(f.relative_to(night))] = sha256sum(f)
        mpath.write_text(json.dumps(m, indent=2, default=str) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date', help='Night, YYYYMMDD')
    p.add_argument('--standard', help='Standard name used in the sens file name (default: TARGNAME)')
    p.add_argument('--reference', help='Reference night: local directory or s3://bucket/prefix')
    p.add_argument('--json', dest='json_out', help='Write the gate results as JSON')
    p.add_argument('--update-manifest', action='store_true',
                   help='Record the results (and sens sha256) in run_manifest.json')
    sys.exit(main(**vars(p.parse_args())))
