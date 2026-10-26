#!/usr/bin/env python
"""Noise budget of the S11 validation case: how much of the variance is source, sky, dark and read noise.

Usage:
    conda run -n pypeit14b python scripts/mosfire/validation_noise_budget.py [--mag-offset 0 4 6]

Reads ``<night>/validation/validation_j0841_summary.json`` (written by
``validate_j0841.py``) and reruns ``compute`` with the same inputs, but a
flat-f_nu source at the measured intrinsic J2 magnitude plus each offset, to
show the regime the measured S/N tested (a bright source constrains the sky
and aperture terms only weakly), and the ETC's response to the D14 sky
measurement and to the D16 aperture scan at fainter magnitudes.
"""
import argparse
import json
import sys

import numpy as np

from keck_etcs import etc, paths


def budget(o, crit, mask):
    S = np.array(o['signal_e'])
    B = np.array(o['sky_e'])
    k = 2.0 if o['meta']['inputs']['nod'] == 'ABBA' else 1.0
    var = np.array(o['noise_e']) ** 2
    m = crit & mask
    return {'source': float(np.median(S[m] / var[m])), 'sky': float(np.median(k * B[m] / var[m])),
            'dark': float(np.median(k * o['dark_e'] / var[m])), 'read': float(np.median(k * o['read_noise_e'] ** 2 / var[m]))}


def main(offsets):
    s = json.loads((paths.night_dir('mosfire', '20220409') / 'validation' / 'validation_j0841_summary.json').read_text())
    base = dict(s['inputs'])
    mag0 = s['measured']['mag_ab_intrinsic_J2']
    e = s['effective_aperture']
    print(f"aperture scan (validation case): band ratio {min(e['scan']['band']):.3f}-{max(e['scan']['band']):.3f} over "
          f"length_fwhm {e['scan']['length_fwhm'][0]}-{e['scan']['length_fwhm'][-1]}; best {e['length_fwhm']}")
    sky_i = s['sky']['ratio_interline_meas_over_gemini']
    for d in offsets:
        inp = {**base, 'spectrum': {'shape': 'flat_fnu'}, 'source': {**base['source'], 'mag': round(mag0 + d, 3)}}
        o = etc.compute(inp)
        w = np.array(o['wave_A'])
        b = np.array(o['sky_e'])
        crit = (w >= 11170) & (w <= 12600)
        inter = b <= 1.25 * np.median(b)
        bi = budget(o, crit, inter)
        snr = np.median(np.array(o['snr_pixel'])[crit & inter])
        o2 = etc.compute({**inp, 'sky_scale': round(sky_i, 4)})
        snr2 = np.median(np.array(o2['snr_pixel'])[crit & inter])
        o3 = etc.compute({**inp, 'aperture': {'length_fwhm': e['length_fwhm']}})
        snr3 = np.median(np.array(o3['snr_pixel'])[crit & inter])
        print(f"J2 = {mag0 + d:6.2f} AB: interline S/N {snr:7.2f}; variance fractions source {bi['source']:.2f} sky "
              f"{bi['sky']:.2f} dark {bi['dark']:.3f} read {bi['read']:.2f}; with sky_scale {sky_i:.2f}: x{snr2 / snr:.3f}; "
              f"with length_fwhm {e['length_fwhm']}: x{snr3 / snr:.3f}")
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--mag-offset', type=float, nargs='+', default=[0.0, 2.0, 4.0, 6.0])
    sys.exit(main(p.parse_args().mag_offset))
