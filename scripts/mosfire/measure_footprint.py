#!/usr/bin/env python
"""Measure the wavelength footprint of a MOSFIRE long-slit setting from a PypeIt WaveCalib file (plan S23d, design 9.2, D56).

Usage:
    conda run -n pypeit14b python scripts/mosfire/measure_footprint.py WaveCalib.fits [WaveCalib.fits ...]
        [--json OUT.json]

For every slit with a wavelength solution: the vacuum wavelength of the
first and last detector pixel along the dispersion axis (``wave_soln``
of PypeIt's fit, 2048 pixels), the number of pixels with a solution, the
mean dispersion, the fit RMS and the file's sha256, which is the
provenance of the footprint frozen into ``keck_etcs.instruments.mosfire``
(``H_FOOTPRINT_A``, ``K_FOOTPRINT_A``; the Y footprint was read the same
way from the dev-suite ``Y_long`` in "Other bands" prompt 1). A long-slit
WaveCalib has one slit; the centred long slit's footprint is what the ETC
models (D58: an off-centre slit loses one band edge in H and K).
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def footprints(path):
    """``[{slit, wave_lo_A, wave_hi_A, n_pix, dispersion_A_per_pix, rms_pix, fwhm_pix}]`` of one WaveCalib file."""
    from pypeit.wavecalib import WaveCalib
    wc = WaveCalib.from_file(str(path), chk_version=False)
    out = []
    for k, wf in enumerate(wc.wv_fits):
        if wf is None or wf.wave_soln is None:
            continue
        w = np.asarray(wf.wave_soln, float)
        good = np.flatnonzero(w > 0)
        if good.size < 2:
            continue
        w0, w1 = float(w[good[0]]), float(w[good[-1]])
        out.append({'slit': int(wc.spat_ids[k]), 'pixel_lo': int(good[0]), 'pixel_hi': int(good[-1]),
                    'wave_lo_A': round(w0, 1), 'wave_hi_A': round(w1, 1), 'n_pix': int(good.size),
                    'dispersion_A_per_pix': round((w1 - w0) / (good[-1] - good[0]), 4),
                    'rms_pix': None if wf.rms is None else round(float(wf.rms), 4),
                    'fwhm_pix': None if wf.fwhm is None else round(float(wf.fwhm), 3)})
    return out


def main(files, json_out=None):
    res = []
    for f in files:
        f = Path(f)
        rec = {'file': str(f), 'sha256': sha256sum(f), 'slits': footprints(f)}
        res.append(rec)
        print(f'{f}\n  sha256 {rec["sha256"]}')
        for s in rec['slits']:
            print(f"  slit {s['slit']}: pixels {s['pixel_lo']}-{s['pixel_hi']} ({s['n_pix']} px): "
                  f"{s['wave_lo_A']:.1f}-{s['wave_hi_A']:.1f} A, {s['dispersion_A_per_pix']:.4f} A/pix, "
                  f"RMS {s['rms_pix']} pix, arc FWHM {s['fwhm_pix']} pix")
    if json_out:
        Path(json_out).write_text(json.dumps(res, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('files', nargs='+')
    p.add_argument('--json', dest='json_out')
    a = p.parse_args()
    sys.exit(main(a.files, a.json_out))
