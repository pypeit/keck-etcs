#!/usr/bin/env python
"""Test the MOSFIRE filter curves with one standard observed in two filters (plan S16).

Usage:
    conda run -n pypeit14b python scripts/mosfire/compare_filter_pair.py CURVE_A.ecsv CURVE_B.ecsv [--png FILE]

Each argument is a harvested curve (``keck_etcs/data/mosfire/throughput/standards/*.ecsv``)
with ``thru_raw`` (zero-point throughput before the filter is divided out) and
``filter_trans`` (the filter curve used). For the same star on nights close
together, ``thru_raw_B / thru_raw_A`` measures ``T_B / T_A`` of the real
filters (plus any change of the rest of the system between the nights), and
should equal ``filter_trans_B / filter_trans_A`` if the filter curves are
right. Prints both ratios in 250 A bins over the overlap of the two curves
and their median, and the implied correction to curve B
(measured / tabulated); ``--png`` plots them.
"""
import argparse
import sys

import numpy as np
from astropy.table import Table


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--png')
    args = ap.parse_args(argv)
    A = Table.read(args.a, format='ascii.ecsv')
    B = Table.read(args.b, format='ascii.ecsv')
    # both curves are on the harvest grid (9000 + k A, 1 A steps) over different ranges: match on wavelength
    wa, wb = np.round(np.asarray(A['wave'], float), 3), np.round(np.asarray(B['wave'], float), 3)
    w, ia, ib = np.intersect1d(wa, wb, return_indices=True)
    if len(w) == 0:
        raise SystemExit('the curves do not overlap')
    ra, rb = np.asarray(A['thru_raw'], float)[ia], np.asarray(B['thru_raw'], float)[ib]
    fa, fb = np.asarray(A['filter_trans'], float)[ia], np.asarray(B['filter_trans'], float)[ib]
    ok = np.isfinite(ra) & np.isfinite(rb) & (fa > 0.5) & (fb > 0.5) & (ra > 0) & (rb > 0)
    meas, tab = rb / ra, fb / fa
    print(f"A {A.meta.get('band')} {A.meta['row']['standard']} {A.meta['row']['date']} | "
          f"B {B.meta.get('band')} {B.meta['row']['standard']} {B.meta['row']['date']}; "
          f"overlap with both filters > 0.5: {w[ok].min():.0f}-{w[ok].max():.0f} A")
    print(f"{'bin [A]':>13s} {'measured B/A':>13s} {'tabulated B/A':>14s} {'meas/tab':>9s}")
    edges = np.arange(np.floor(w[ok].min() / 250) * 250, w[ok].max() + 250, 250)
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = ok & (w >= lo) & (w < hi)
        if s.sum() < 20:
            continue
        m, t = np.median(meas[s]), np.median(tab[s])
        print(f'{lo:6.0f}-{hi:6.0f} {m:13.3f} {t:14.3f} {m / t:9.3f}')
    m, t = np.median(meas[ok]), np.median(tab[ok])
    print(f"{'overlap':>13s} {m:13.3f} {t:14.3f} {m / t:9.3f}  <- curve B correction (measured / tabulated)")
    if args.png:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(w[ok], meas[ok], lw=0.6, label='measured thru_raw B/A')
        ax.plot(w[ok], tab[ok], lw=1.2, label='tabulated filter B/A')
        ax.set_xlabel('wavelength [A]')
        ax.set_ylabel('ratio')
        ax.legend()
        fig.tight_layout()
        fig.savefig(args.png, dpi=110)
        print(f'wrote {args.png}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
