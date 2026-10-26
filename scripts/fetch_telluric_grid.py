#!/usr/bin/env python
"""Fetch the PypeIt telluric grid used by the MOSFIRE sensfunc and record its sha256.

Usage:
    conda run -n pypeit14b python scripts/fetch_telluric_grid.py [--force-update]

Asks PypeIt for ``TellPCA_3000_26000_R10000.fits`` through
``pypeit.dataPaths.telgrid`` (host ``s3_cloud``, i.e. Nautilus S3, see
``pypeit/data/s3_url.txt``). PypeIt keeps the file in its astropy cache
(``pkgname='pypeit'``), keyed by the permanent URL
``https://s3.cloud.com/pypeit/telluric/atm_grids/<file>``; the real download
source is ``https://<s3_url.txt>/pypeit/telluric/atm_grids/<file>``.

Prints whether the file was already cached, the cached path, size and
sha256, and writes the sha256 as one line to ``nautilus/telluric_grid.sha256``
(the image build checks its own download against it).
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

import astropy.utils.data
from astropy.io import fits

from pypeit import dataPaths
from pypeit.pkg import cache

TELGRID = 'TellPCA_3000_26000_R10000.fits'
REPO = Path(__file__).resolve().parents[1]
SHA_FILE = REPO / 'nautilus' / 'telluric_grid.sha256'


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def main(force_update=False):
    telgrid = dataPaths.telgrid
    subdir = str(telgrid.path.relative_to(telgrid.data))
    cache_url, sources = cache._build_remote_url(TELGRID, subdir, remote_host=telgrid.host)
    was_cached = astropy.utils.data.is_url_in_cache(cache_url, pkgname='pypeit')
    in_pkg = (telgrid.path / TELGRID).is_file()

    print(f'PypeIt data path : {telgrid.path} (host {telgrid.host})')
    print(f'Cache key        : {cache_url}')
    print(f'Download source  : {sources[0] if sources else cache_url}')
    if in_pkg:
        status = 'in the package tree (no cache lookup)'
    elif was_cached and not force_update:
        status = 'already cached, not downloading'
    else:
        status = 'downloading' + (' (forced update)' if force_update else '')
    print(f'Status           : {status}')

    path = Path(telgrid.get_file_path(TELGRID, force_update=force_update))
    size = path.stat().st_size
    digest = sha256sum(path)
    with fits.open(path) as hdul:
        hdus = [f'{h.name}{"" if h.data is None else list(h.data.shape)}' for h in hdul]

    print(f'Cached path      : {path}')
    print(f'Size             : {size} bytes ({size / 1e6:.2f} MB)')
    print(f'sha256           : {digest}')
    print(f'HDUs             : {", ".join(hdus)}')

    hits = cache.search_cache(TELGRID)
    print(f"search_cache('{TELGRID}'): {len(hits)} path(s)")
    for h in hits:
        print(f'  {h}')
    others = {k: v for k, v in cache.search_cache('TellPCA', path_only=False).items()
              if TELGRID not in k}
    if others:
        print('Other TellPCA grids in the cache (not used by MOSFIRE J):')
        for k, v in others.items():
            print(f'  {k.rsplit("/", 1)[-1]}  {v}')

    SHA_FILE.parent.mkdir(parents=True, exist_ok=True)
    SHA_FILE.write_text(digest + '\n')
    print(f'Wrote {SHA_FILE.relative_to(REPO)}')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--force-update', action='store_true',
                        help='Re-download the file into the cache even if it is cached')
    sys.exit(main(**vars(parser.parse_args())))
