"""Count how many wide-slit standards each candidate outlier rule would exclude.

Supports Q&A H-5 of ``claude_prompts/keck_mosfire/keck_mosfire_prompt_H.md``
(2026-11-04). The rule (D22, ``combine.MAD_CLIP``) excludes a night whose
band median lies more than 3 MAD from the era median. Until H-5 a row
flagged ``excluded_3mad`` by an earlier combine took no part in the next
one, so the exclusion ratcheted across reruns (8 of 25 H rows after two
reruns); since H-5 (answer (a)) each combine is one fresh pass, which is
the ``3 MAD`` / ``one pass`` column here. This script rebuilds the
statistics from the ``thru_median_common`` column of ``standards.ecsv``
alone (no flags, no curve files) and reports, per band and era, what a
single pass and an iterated-to-convergence pass of each rule would
exclude:

- ``3 MAD`` (the committed rule),
- ``5 MAD``,
- ``max(3 MAD, 3 %)`` and ``max(3 MAD, 5 %)`` of the era median (a floor so
  a tight MAD cannot clip ordinary nights),
- ``3 MAD low only`` (clouds only lower a wide-slit throughput; a high
  outlier is kept).

``thru_median_common`` is the harvest's band median over the common window,
the same statistic combine clips on. Rows flagged ``excluded_nonlinear`` or
``narrow`` are left out as in combine.

Usage::

    conda run -n pypeit14b python scripts/mosfire/scan_clip_rule.py [--band H]
"""
import argparse
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs.instruments.mosfire import MOSFIRE
from keck_etcs.calib.combine import in_era

ROOT = Path(__file__).resolve().parents[2]
STANDARDS = ROOT / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'standards.ecsv'

RULES = {
    '3 MAD': dict(k=3.0, floor=0.0, low_only=False),
    '5 MAD': dict(k=5.0, floor=0.0, low_only=False),
    'max(3 MAD, 3%)': dict(k=3.0, floor=0.03, low_only=False),
    'max(3 MAD, 5%)': dict(k=3.0, floor=0.05, low_only=False),
    '3 MAD low only': dict(k=3.0, floor=0.0, low_only=True),
}


def clip_once(vals, k, floor, low_only):
    """Indices excluded by one pass of the rule over ``vals``."""
    if len(vals) < 3:
        return []
    med = np.median(vals)
    mad = np.median(np.abs(vals - med))
    thr = max(k * mad, floor * med)
    if thr <= 0:
        return []
    dev = vals - med
    out = (dev < -thr) if low_only else (np.abs(dev) > thr)
    return list(np.flatnonzero(out))


def clip_iterated(vals, **rule):
    """Indices excluded when the rule is reapplied to the survivors until nothing changes."""
    alive = np.arange(len(vals))
    gone = []
    while True:
        out = clip_once(vals[alive], **rule)
        if not out:
            return gone
        gone.extend(alive[out].tolist())
        alive = np.delete(alive, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--band', default=None, help='one filter (default: every band in the table)')
    args = ap.parse_args(argv)
    t = Table.read(STANDARDS)
    bands = [args.band] if args.band else sorted(set(str(f) for f in t['filter']))
    for band in bands:
        rows = t[t['filter'] == band]
        print(f'band {band}: {len(rows)} rows in {STANDARDS.relative_to(ROOT)}')
        for era in MOSFIRE.eras:
            sel = [r for r in rows if in_era(r['date'], era) and 'excluded_nonlinear' not in str(r['flag'])
                   and 'narrow' not in str(r['flag'])]
            if not sel:
                continue
            vals = np.array([float(r['thru_median_common']) for r in sel])
            med = np.median(vals)
            mad = np.median(np.abs(vals - med))
            print(f'  era {era.name}: {len(vals)} wide-slit rows, median {med:.4f}, MAD {mad:.4f} '
                  f'({100 * mad / med:.1f} %), 3 MAD = {100 * 3 * mad / med:.1f} %')
            print(f'    {"rule":18s} {"one pass":>9s} {"iterated":>9s}  survivors median  excluded (one pass)')
            for name, rule in RULES.items():
                one = clip_once(vals, **rule)
                it = clip_iterated(vals, **rule)
                keep = np.delete(vals, one)
                who = ', '.join(f"{sel[i]['standard']} {sel[i]['date']} {vals[i]:.3f}" for i in one)
                print(f'    {name:18s} {len(one):>9d} {len(it):>9d}  {np.median(keep):.4f}            {who}')
            flagged = [r for r in sel if 'excluded_3mad' in str(r['flag'])]
            print(f'    committed table: {len(flagged)} row(s) carry excluded_3mad')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
