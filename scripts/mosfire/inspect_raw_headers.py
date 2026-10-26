#!/usr/bin/env python
"""Print the environment-related cards of raw MOSFIRE frames.

Answers two open items of the Y/H/K design (design 9.5, P13 and P14):
whether any header card carries the dome or mirror temperature (for the
K thermal term) and whether any carries the Moon (for the sky-excess
frame selection). Run in ``pypeit14b``::

    conda run -n pypeit14b python scripts/mosfire/inspect_raw_headers.py \
        [FITS ...] [--pattern REGEX]

With no files it reads the first frame of the dev-suite ``K_long``,
``Y_long``, ``longslit_3x0.7_K`` and ``J2_long`` directories under
``$PYPEIT_DEV/RAW_DATA/keck_mosfire`` (default
``~/Projects/PypeIt/PypeIt-development-suite``).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from astropy.io import fits

DEFAULT_PATTERN = (r"TEMP|TMP|MOON|SUN|DOME|MIRR|WX|HUMID|PRESS|WIND|DEWP|"
                   r"AMBIENT|OUTSIDE|SKYPA|EL\b|AIRMASS|MJD|DATE-OBS|UTC|"
                   r"SAMPMODE|NUMREADS|TRUITIME|FILTER|MASKNAME|GRATMODE|"
                   r"OBJECT|TARGNAME")

DEV_SETUPS = ["K_long", "Y_long", "longslit_3x0.7_K", "J2_long"]


def default_files() -> list[Path]:
    root = Path(os.environ.get(
        "PYPEIT_DEV", Path.home() / "Projects/PypeIt/PypeIt-development-suite"))
    out = []
    for setup in DEV_SETUPS:
        d = root / "RAW_DATA/keck_mosfire" / setup
        frames = sorted(d.glob("m*.fits"))
        if frames:
            out.append(frames[0])
    return out


def summarise(files: list[Path], key: str, by_night: bool) -> int:
    """Count, min, median and max of a numeric card over ``files``."""
    import numpy as np
    vals, nights, missing = [], [], 0
    for path in files:
        hdr = fits.getheader(path)
        if key not in hdr:
            missing += 1
            continue
        try:
            vals.append(float(hdr[key]))
        except (TypeError, ValueError):
            missing += 1
            continue
        nights.append(str(hdr.get("DATE-OBS", "?"))[:10])
    v = np.array(vals)
    print(f"{key}: {len(v)} frames with the card, {missing} without")
    if len(v):
        print(f"  min {v.min():.2f}  median {np.median(v):.2f}  max {v.max():.2f}")
    if by_night and len(v):
        for night in sorted(set(nights)):
            sel = v[np.array(nights) == night]
            print(f"  {night}: n={len(sel):3d}  median {np.median(sel):6.2f}"
                  f"  range {sel.min():6.2f} .. {sel.max():6.2f}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN,
                    help="regex matched (case-insensitive) against card names "
                         "and comments")
    ap.add_argument("--all", action="store_true", help="print every card")
    ap.add_argument("--stat", metavar="KEY",
                    help="instead of printing cards, summarise this numeric "
                         "card over all files (count, min, median, max; "
                         "per-night medians when --by-night)")
    ap.add_argument("--by-night", action="store_true",
                    help="with --stat, also print the median per DATE-OBS")
    args = ap.parse_args(argv)

    files = args.files or default_files()
    if not files:
        print("no files found", file=sys.stderr)
        return 1
    if args.stat:
        return summarise(files, args.stat, args.by_night)
    rx = re.compile(args.pattern, re.IGNORECASE)
    for path in files:
        hdr = fits.getheader(path)
        print(f"\n=== {path}  ({len(hdr)} cards)")
        for card in hdr.cards:
            key = card.keyword
            if not key or key in ("COMMENT", "HISTORY"):
                continue
            if args.all or rx.search(key) or rx.search(str(card.comment)):
                print(f"  {key:8s} = {str(card.value)[:40]:40s} / {card.comment}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
