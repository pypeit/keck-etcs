#!/usr/bin/env python
"""Empirical MOSFIRE read noise from pairs of CDS lamp-off flats (plan S17).

Usage:
    conda run -n pypeit14b python scripts/mosfire/measure_read_noise.py
        [--night 20220409] [--frames 22 23 24 25 26] [--gain 2.15] [--json FILE]

The 2022-04-09 lamp-off dome flats m220409_0022-0026 are CDS reads
(``SAMPMODE = 2``, ``NUMREADS = 1``, 8.7 s, J2, ``BUNIT = 'ADU per coadd'``,
one coadd). For each consecutive pair the difference removes the fixed
pattern (bias, reference offsets, dome signal); its 4-sigma-clipped
standard deviation divided by sqrt(2) and multiplied by the gain is the
per-frame noise in electrons.

The statistic is taken in 64 x 64 pixel tiles over the data section
``[5:2044, 5:2044]`` (PypeIt's ``datasec``, 1-indexed); a tile is
"low-signal" when the pair's median level is below ``--max-signal`` ADU
(the frames are mostly the dark CSU bars). Per tile the photon noise of the
residual signal is also removed, ``RN^2 = sigma_e^2 - S_e``, with ``S_e``
the tile's mean level in electrons (clipped at 0). Reported: the median and
16/84th percentiles over the low-signal tiles, raw and photon-corrected,
for each pair and all pairs; compared with the Keck CDS value, 21 e-.

Read-only; writes only the optional JSON summary.
"""
import argparse
import json
import sys

import numpy as np
from astropy.io import fits
from astropy.stats import sigma_clipped_stats

from keck_etcs import paths

KECK_CDS_RN = 21.0
TILE = 64
DATASEC = (slice(4, 2044), slice(4, 2044))


def robust_std(x):
    # clipped standard deviation, not 1.4826 MAD: the raw CDS frames come in 0.5 ADU steps, which
    # quantize a MAD of a few ADU
    return float(sigma_clipped_stats(x, sigma=4.0, maxiters=5)[2])


def pair_tiles(a, b, gain, max_signal):
    """Per-tile (signal ADU, raw RN e-, photon-corrected RN e-) for one pair, low-signal tiles only."""
    d = (a - b)[DATASEC]
    m = (0.5 * (a + b))[DATASEC]
    out = []
    ny, nx = d.shape
    for y in range(0, ny - TILE + 1, TILE):
        for x in range(0, nx - TILE + 1, TILE):
            dt, mt = d[y:y + TILE, x:x + TILE], m[y:y + TILE, x:x + TILE]
            s = float(np.median(mt))
            if s > max_signal:
                continue
            sig_e = robust_std(dt) / np.sqrt(2) * gain
            s_e = max(s, 0.0) * gain
            out.append((s, sig_e, float(np.sqrt(max(sig_e ** 2 - s_e, 0.0)))))
    return np.array(out)


def summary(arr):
    p16, p50, p84 = np.percentile(arr, [16, 50, 84])
    return {'median': round(float(p50), 2), 'p16': round(float(p16), 2), 'p84': round(float(p84), 2)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--night', default='20220409')
    p.add_argument('--frames', type=int, nargs='+', default=[22, 23, 24, 25, 26])
    p.add_argument('--gain', type=float, default=2.15)
    p.add_argument('--max-signal', type=float, default=10.0, help='low-signal tile threshold [ADU]')
    p.add_argument('--json')
    args = p.parse_args()

    raw = paths.data_root() / 'mosfire' / args.night / 'raw'
    frames = {}
    for n in args.frames:
        f = raw / f'm{args.night[2:]}_{n:04d}.fits'
        with fits.open(f) as h:
            hdr = h[0].header
            frames[n] = h[0].data.astype(float)
            print(f"{f.name}: SAMPMODE {hdr.get('SAMPMODE')} NUMREADS {hdr.get('NUMREADS')} "
                  f"COADDS {hdr.get('COADDS')} TRUITIME {hdr.get('TRUITIME'):.2f} s FLATSPEC {hdr.get('FLATSPEC')} "
                  f"BUNIT {hdr.get('BUNIT')!r}, median {np.median(frames[n][DATASEC]):.1f} ADU")
            if hdr.get('SAMPMODE') != 2 or hdr.get('NUMREADS') != 1:
                print(f'  {f.name} is not CDS; stop')
                return 1

    result = {'night': args.night, 'gain': args.gain, 'tile': TILE, 'max_signal_adu': args.max_signal,
              'keck_cds_rn': KECK_CDS_RN, 'pairs': {}}
    allt = []
    print(f'\nper pair (tiles {TILE}x{TILE} with median level <= {args.max_signal} ADU):')
    for a, b in zip(args.frames[:-1], args.frames[1:]):
        t = pair_tiles(frames[a], frames[b], args.gain, args.max_signal)
        allt.append(t)
        raw_s, cor_s = summary(t[:, 1]), summary(t[:, 2])
        full = robust_std((frames[a] - frames[b])[DATASEC]) / np.sqrt(2) * args.gain
        result['pairs'][f'{a}-{b}'] = {'n_tiles': len(t), 'rn_raw': raw_s, 'rn_photon_corrected': cor_s,
                                       'rn_full_datasec': round(full, 2)}
        print(f'  {a:04d}-{b:04d}: {len(t):4d} tiles, RN raw {raw_s["median"]:.2f} '
              f'[{raw_s["p16"]:.2f}, {raw_s["p84"]:.2f}] e-, photon-corrected {cor_s["median"]:.2f} e-; '
              f'whole datasec {full:.2f} e-')
    allt = np.vstack(allt)
    raw_s, cor_s = summary(allt[:, 1]), summary(allt[:, 2])
    result['all'] = {'n_tiles': len(allt), 'rn_raw': raw_s, 'rn_photon_corrected': cor_s,
                     'ratio_to_keck_cds': round(cor_s['median'] / KECK_CDS_RN, 3)}
    print(f'\nall pairs: {len(allt)} tiles, RN raw {raw_s["median"]:.2f} [{raw_s["p16"]:.2f}, {raw_s["p84"]:.2f}] e-, '
          f'photon-corrected {cor_s["median"]:.2f} [{cor_s["p16"]:.2f}, {cor_s["p84"]:.2f}] e-')
    print(f'Keck CDS table value {KECK_CDS_RN} e-: measured/table = {cor_s["median"] / KECK_CDS_RN:.3f}')
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(result, f, indent=2)
        print(f'wrote {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
