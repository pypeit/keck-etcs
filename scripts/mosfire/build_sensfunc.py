#!/usr/bin/env python
"""Build the sensitivity function(s) for one MOSFIRE night's standard, in one band.

Usage:
    conda run -n pypeit14b python scripts/mosfire/build_sensfunc.py DATE
        [--band H] [--standard NAME] [--sens FILE] [--frames-only]

``--band`` (default ``$BAND``, then ``$FILTER``, from the night manifest)
selects the night's product directory (``mosfire/<night>/<band>/`` for Y,
H and K; the night level for J, J2 and J3; design D55) and the default
``.sens`` file of the band's group (``keck_etcs.instruments.mosfire.sens_par_file``:
``keck_mosfire_{J,H,K}.sens``; H and K provisional until S24a).

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

``--sens`` defaults to the band's file (above). Each PypeIt call is logged
to ``sens/<output stem>.log``.

Y, H and K (plan S24a, design D53; the J group keeps PypeIt's defaults so
that the released J products stay reproducible until the next J
re-reduction): two band-neutral settings that the H polyorder test showed
to matter for a star in a wide ``long2pos_specphot`` bar:

- **filter-edge mask** (:data:`FILTER_MASK_FRAC`): pixels where the band's
  filter transmission is below half its peak are masked in copies of the
  spec1d files (``sens/spec1d_<frame>_fmask.fits``, ``OPT_MASK``/``BOX_MASK``)
  before the per-frame fits and the coadd, so that the polynomial zero
  point is fitted only where the filter is open. Off-centre bars see
  300 A beyond the filter's half-maximum, where the steep zero point
  pulls a low-order polynomial off by 10-30 percent inside the window;
- **telluric resolution guess** (``[[IR]] resln_guess`` and
  ``resln_frac_bounds``): PypeIt guesses the resolution from the pixel
  sampling (3 pixels per element) and bounds the fit to 0.6-1.4 of it,
  which pins a 4" bar's fit at the lower bound. The guess is set from the
  band's LSF rule (``MOSFIRE.lsf_fwhm_pix``) at the effective slit width,
  the smaller of the slit (bar) width and the star's spatial FWHM, at the
  band's middle node, with the bounds widened to :data:`RESLN_FRAC_BOUNDS`
  (a star in a wide bar still fitted below 0.6x the seeing-based guess).
  The lines are written into ``sens/<NAME>_<DATE>_{A0V,std}.sens``, and
  ``sens/<NAME>_<DATE>_sens_setup.json`` records both settings.

A0V standards (design D2, N3, D51; plans S15a, S24a): with ``--std-class A0V``
and ``--mag`` (defaults: the night-manifest columns ``std_class`` and the
band's 2MASS column, ``jmag_2mass`` for Y and the J group, ``hmag_2mass``
for H, ``kmag_2mass`` for K, which the night job exports as ``STD_CLASS``
and ``JMAG_2MASS``/``HMAG_2MASS``/``KMAG_2MASS``; ``--jmag`` is the J
magnitude, the model's for the J group and the cross-check elsewhere), the
``.sens`` file is copied to ``sens/<NAME>_<DATE>_A0V.sens`` with
``star_type = A0`` and ``star_mag = V_eq`` added under ``[sensfunc]``:
PypeIt's Vega model scaled to the star's 2MASS magnitude in the band's own
2MASS band (``keck_etcs.calib.standards.a0v_model(band, mag)``). The model
record (``mag_2mass``, ``band_2mass``, ``j_2mass``, ``a0v_jhk_offset_mag``)
is written to ``sens/<NAME>_<DATE>_std_model.json``. Archive standards
(white dwarfs) need nothing: PypeIt finds them by position.
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
FILTER_MASK_FRAC = 0.5          # pixels with filter transmission below this fraction of the peak are masked
EDGE_GROUPS = ('Y', 'H', 'K')   # band groups with the filter-edge mask and the resolution guess (J frozen)
RESLN_FRAC_BOUNDS = (0.4, 1.5)  # PypeIt's resln_frac_bounds (default 0.6-1.4): a star in a wide bar sat at 0.6x
DEFAULT_SENS = REPO / 'keck_etcs' / 'data' / 'pypeit_par' / 'keck_mosfire_J.sens'


def default_sens(band):
    """The ``.sens`` file of a band's group (the J file for None or an unknown band)."""
    from keck_etcs.instruments.base import DATA_DIR
    from keck_etcs.instruments import mosfire
    try:
        return DATA_DIR / mosfire.sens_par_file(band)
    except KeyError:
        return DEFAULT_SENS


def run(cmd, log, cwd):
    print(f'$ {" ".join(str(c) for c in cmd)}  (log {log.name})', flush=True)
    with open(log, 'w') as f:
        rc = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT,
                            cwd=cwd).returncode
    if rc != 0:
        raise RuntimeError(f'{cmd[0]} failed (exit {rc}); see {log}')


def slit_width_of(manifest, obj):
    """Slit (bar) width [arcsec] of an object: the specphot bar table, else the mask name (``LONGSLIT-3x0.7``)."""
    import re
    sp = manifest.get('specphot') or {}
    for b in sp.get('bars', []):
        if int(b['spat_id']) == int(obj.get('slit', -1)):
            return float(b['width_arcsec'])
    frames = {f['filename']: f for f in manifest['frames']}
    for key in ('maskname', 'decker', 'slit'):
        v = frames.get(obj['frame'], {}).get(key) or manifest.get(key)
        m = re.search(r'x([0-9.]+)', str(v or ''))
        if m:
            return float(m.group(1))
    return None


def resln_guess(band, width_eff):
    """PypeIt's ``resln_guess`` (R = lambda / FWHM) from the band's LSF rule at the effective slit width."""
    from keck_etcs.instruments.mosfire import MOSFIRE
    b = MOSFIRE.bands[str(band)]
    fwhm_pix, source = MOSFIRE.lsf_fwhm_pix(float(width_eff), band)
    lam = float(b.zp_nodes_A[1]) if b.zp_nodes_A else float(np.mean(b.footprint_A))
    return lam / (fwhm_pix * float(b.dispersion_A_per_pix)), fwhm_pix, source


def filter_window(band, frac=FILTER_MASK_FRAC):
    """``(lo, hi)`` A where the band's filter transmission is at least ``frac`` of its peak."""
    from keck_etcs.instruments.mosfire import MOSFIRE
    fc = MOSFIRE.filter_curve(str(band))
    w, tr = fc['wave_A'], fc['transmission']
    s = tr >= frac * np.nanmax(tr)
    return float(w[s].min()), float(w[s].max())


def mask_spec1d(src, dst, window):
    """A copy of a spec1d with ``OPT_MASK``/``BOX_MASK`` false outside ``window`` (the filter-edge mask)."""
    from pypeit.specobjs import SpecObjs
    sobjs = SpecObjs.from_fitsfile(str(src), chk_version=False)
    n_masked = 0
    for so in sobjs:
        for wcol, mcol in (('OPT_WAVE', 'OPT_MASK'), ('BOX_WAVE', 'BOX_MASK')):
            if so[wcol] is not None and so[mcol] is not None:
                inside = (so[wcol] >= window[0]) & (so[wcol] <= window[1])
                n_masked += int(np.sum(so[mcol] & ~inside))
                so[mcol] = so[mcol] & inside
    sobjs.write_to_fits(sobjs.header, str(dst), overwrite=True)
    return n_masked


def with_resln(text, setup):
    """The ``.sens`` text with ``resln_guess`` under ``[[IR]]`` when the setup has one (replacing any present)."""
    import re
    if not setup.get('resln_guess'):
        return text
    v = setup['resln_guess']['value']
    lo, hi = RESLN_FRAC_BOUNDS
    for key, val in (('resln_guess', f'{v:.1f}'), ('resln_frac_bounds', f'{lo:g}, {hi:g}')):
        text, k = re.subn(rf'(?m)^(\s*{key}\s*=\s*).*$', rf'\g<1>{val}', text)
        if k == 0:
            if '[[IR]]\n' in text:
                text = text.replace('[[IR]]\n', f'[[IR]]\n    {key} = {val}\n', 1)
            else:
                text += f'  [[IR]]\n    {key} = {val}\n'
    setup['resln_guess']['frac_bounds'] = list(RESLN_FRAC_BOUNDS)
    return text


def main(date, standard=None, sens=None, frames_only=False, std_class=None, jmag=None, band=None, mag=None):
    band = band or os.environ.get('BAND') or os.environ.get('FILTER') or None
    night = paths.night_dir('mosfire', date, band=band)
    manifest = json.loads((night / 'run_manifest.json').read_text())
    band = band or manifest.get('band') or manifest.get('filter')
    sens = Path(sens) if sens else default_sens(band)
    print(f'band {band}: products in {night}; sens parameters {sens}')
    outdir = night / 'sens'
    outdir.mkdir(parents=True, exist_ok=True)
    std_class = std_class if std_class is not None else os.environ.get('STD_CLASS') or None
    jmag = jmag if jmag is not None else (float(os.environ['JMAG_2MASS']) if os.environ.get('JMAG_2MASS') else None)
    from keck_etcs.calib import standards
    tb = standards.tmass_band(band) if band else 'J'
    if mag is None:
        mag = standards.mag_from_env(band) if band else None
    if mag is None and tb == 'J':
        mag = jmag

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
    group = None
    if band:
        from keck_etcs.instruments.mosfire import MOSFIRE
        group = MOSFIRE.group_of(band)
    edge = group in EDGE_GROUPS
    setup = {'band': band, 'group': group, 'filter_mask': None, 'resln_guess': None}
    spec1d_of = {o['frame']: night / 'redux' / 'Science' / o['spec1d'] for o in objs}
    if edge:
        window = filter_window(band)
        setup['filter_mask'] = {'frac_of_peak': FILTER_MASK_FRAC, 'window_A': list(window), 'n_masked': {}}
        for o in objs:
            dst = outdir / f"{Path(o['spec1d']).stem}_fmask.fits"
            setup['filter_mask']['n_masked'][o['frame']] = mask_spec1d(spec1d_of[o['frame']], dst, window)
            spec1d_of[o['frame']] = dst
        print(f'filter-edge mask (D53, S24a): fit only {window[0]:.0f}-{window[1]:.0f} A '
              f'(transmission >= {FILTER_MASK_FRAC:g} of the {band} peak); masked copies sens/spec1d_*_fmask.fits')
        widths = [slit_width_of(manifest, o) for o in objs]
        fwhms = [o['fwhm_arcsec'] for o in objs if o.get('fwhm_arcsec')]
        slit_w = min(w for w in widths if w is not None) if any(w is not None for w in widths) else None
        seeing = float(np.median(fwhms)) if fwhms else None
        width_eff = min(x for x in (slit_w, seeing) if x is not None) if (slit_w or seeing) else None
        if width_eff:
            r, fwhm_pix, source = resln_guess(band, width_eff)
            setup['resln_guess'] = {'value': round(r, 1), 'width_eff_arcsec': round(width_eff, 3),
                                    'slit_width_arcsec': slit_w, 'seeing_fwhm_arcsec': seeing,
                                    'lsf_fwhm_pix': round(fwhm_pix, 3), 'lsf_source': source}
            print(f'resln_guess {r:.0f} (R = lambda / FWHM at the effective slit {width_eff:.2f}": slit {slit_w}, '
                  f'star FWHM {seeing if seeing is None else round(seeing, 2)}"; LSF {fwhm_pix:.2f} pix, {source})')
    if std_class and str(std_class).upper().startswith('A0'):
        if mag is None:
            print(f'A0V standard without a 2MASS {tb} magnitude (--mag or ${standards.mag_column(band or "J").upper()})')
            return 1
        text, rec = standards.write_sens_par(sens.read_text(), mag, band or 'J', j_mag=jmag)
        sens = outdir / f'{name}_{date}_A0V.sens'
        sens.write_text(with_resln(text, setup))
        rec.update({'standard': name, 'std_class': 'A0V', 'sens_par': sens.name})
        (outdir / f'{name}_{date}_std_model.json').write_text(json.dumps(rec, indent=1) + '\n')
        print(f"A0V model: 2MASS {tb} {mag} -> PypeIt Vega model at V_eq {rec['v_equivalent']} ({sens.name})"
              + (f"; J-scaled model offset {rec['a0v_jhk_offset_mag']:+.4f} mag (D51 cross-check)"
                 if rec.get('a0v_jhk_offset_mag') is not None and tb != 'J' else ''))

    else:
        if setup['resln_guess']:
            text = with_resln(sens.read_text(), setup)
            sens = outdir / f'{name}_{date}_std.sens'
            sens.write_text(text)
    setup['sens_par'] = sens.name
    (outdir / f'{name}_{date}_sens_setup.json').write_text(json.dumps(setup, indent=1) + '\n')

    # 1. per frame
    for o in objs:
        frameno = Path(o['frame']).stem.split('_')[-1]
        out = outdir / f'sens_{name}_{date}_{frameno}.fits'
        run(['pypeit_sensfunc', spec1d_of[o['frame']], '-s', sens, '-o', out],
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
    rows = '\n'.join(f'    {spec1d_of[o["frame"]]} | {o["name"]}' for o in objs)
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
    parser.add_argument('--mag', type=float, help="2MASS magnitude of an A0V standard in the band's 2MASS band (D51; "
                                                   "default: $JMAG_2MASS, $HMAG_2MASS or $KMAG_2MASS by band)")
    parser.add_argument('--jmag', type=float, help='2MASS J of an A0V standard (default: $JMAG_2MASS; the model '
                                                    'magnitude for Y and the J group, the cross-check for H and K)')
    parser.add_argument('--band', help='band of the products (default: $BAND, $FILTER; D55 layout)')
    sys.exit(main(**vars(parser.parse_args())))
