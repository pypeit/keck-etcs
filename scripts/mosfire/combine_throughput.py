#!/usr/bin/env python
"""Write the per-era MOSFIRE throughput products from the harvested standards (plan S10, design 4.5).

Usage:
    conda run -n pypeit14b python scripts/mosfire/combine_throughput.py

Reads ``keck_etcs/data/mosfire/throughput/standards.ecsv`` and its curves,
combines, for every band group that has rows (design D49: J = J/J2 today),
each era of ``keck_etcs.instruments.mosfire`` that has standards with
``keck_etcs.calib.combine.combine_era``, and writes
``keck_etcs/data/mosfire/throughput/mosfire_thru_<group>_<era tag>.ecsv``
(``wave, thru_median, thru_mad, n_std``; ``Instrument.throughput_file``),
registered in ``keck_etcs/data/index.yaml`` under ``calib_version =
CALIB_VERSION`` with the ``bands`` the file covers. Nights excluded by the
3-MAD rule get ``excluded_3mad`` in their ``flag`` in ``standards.ecsv``.
Eras without standards get no file; ``compute`` then uses the nearest era of
the group that has one, with a warning, or the group's provisional
placeholder when no era has one (S23a).

Set ``CALIB_VERSION`` to the release tag (``mosfire-YYYY.MM``) before a
release (``nautilus/README.md`` section 10).
"""
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table

import keck_etcs
from keck_etcs.calib.combine import combine_era
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
THRU = DATA_DIR / 'mosfire' / 'throughput'
INDEX = DATA_DIR / 'index.yaml'
CALIB_VERSION = 'mosfire-2026.10'
SCRIPT = 'scripts/mosfire/combine_throughput.py'


def write_index(entries):
    index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {}).update(entries)
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def main():
    rows = Table.read(THRU / 'standards.ecsv', format='ascii.ecsv')
    curves = {str(r['thru_curve_file']): Table.read(THRU / str(r['thru_curve_file']), format='ascii.ecsv')
              for r in rows}
    filters = {}
    for band in {str(b) for b in rows['filter']}:
        f = MOSFIRE.filter_curve(band)
        filters[band] = (f['wave_A'], f['transmission'], tuple(f['meta']['half_power_A']))
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    entries, excluded = {}, []
    groups = sorted({MOSFIRE.group_of(str(b)) for b in rows['filter']})
    for group in groups:
        group_bands = MOSFIRE.group_bands(group)
        window = MOSFIRE.common_window(group)
        nodes = next(MOSFIRE.bands[b].zp_nodes_A for b in group_bands if MOSFIRE.bands[b].zp_nodes_A)
        for era in MOSFIRE.eras:
            # per-band rules (common window, edge trim, A0V cut) from the instrument module (S23a)
            t, info = combine_era(rows, curves, era, filters, bands=MOSFIRE.bands, group=group)
            if t is None:
                print(f'group {group}, era {era.name}: no standards; no file')
                continue
            excluded += [(str(p['row']['standard']), str(p['row']['date'])) for p in info['excluded']]
            t.meta = {
                'description': f'MOSFIRE filter-free throughput (telescope + spectrograph + detector), '
                               f'{group} band group, era {era.name} (design 4.5): pixel-wise median of the standards',
                'instrument': 'keck_mosfire', 'band_group': group, 'bands': list(group_bands),
                'band': f'{group} grating order, filter-free ({", ".join(group_bands)})',
                'common_window_A': [float(window[0]), float(window[1])],
                **t.meta,
                'n_standards': len(info['used']), 'calib_version': CALIB_VERSION,
                'keck_etcs_version': keck_etcs.__version__, 'created': now, 'script': SCRIPT,
                'source_table': 'mosfire/throughput/standards.ecsv',
            }
            rel = MOSFIRE.throughput_file(era, group)
            t.write(DATA_DIR / rel, format='ascii.ecsv', overwrite=True)
            entries[rel] = {
                'calib_version': CALIB_VERSION, 'bands': list(group_bands), 'created': now,
                'sha256': hashlib.sha256((DATA_DIR / rel).read_bytes()).hexdigest(), 'script': SCRIPT,
                'pypeit_version': ','.join(t.meta['pypeit_versions']),
                'provenance': f"{group} group, era {era.name}: median of {len(info['used'])} standard(s) "
                              f"({', '.join(s['standard'] + ' ' + s['date'] for s in t.meta['standards'])}); "
                              f"images {', '.join(t.meta['images'])}; PypeIt {', '.join(t.meta['pypeit_git_shas'])}"}
            print(f"group {group}, era {era.name}: {len(info['used'])} standard(s), {len(info['excluded'])} excluded; "
                  f"{t.meta['valid_range_A'][0]:.0f}-{t.meta['valid_range_A'][1]:.0f} A; band median "
                  f"{t.meta['band_median_era']} ({window[0]:.0f}-{window[1]:.0f} A); {t.meta['filter_handling']}; "
                  f"images {t.meta['images']} -> {rel}")
            for lam in sorted(set(nodes) | {window[0], window[1]}):
                if t['wave'][0] <= lam <= t['wave'][-1]:
                    print(f'    {lam:.0f} A: thru {np.interp(lam, t["wave"], t["thru_median"]):.4f}')
    if excluded:
        for r in rows:
            if (str(r['standard']), str(r['date'])) in excluded and 'excluded_3mad' not in str(r['flag']):
                r['flag'] = 'excluded_3mad' if str(r['flag']) in ('ok', '') else f"{r['flag']},excluded_3mad"
        rows.write(THRU / 'standards.ecsv', format='ascii.ecsv', overwrite=True)
        idx = yaml.safe_load(INDEX.read_text())['files']['mosfire/throughput/standards.ecsv']
        idx['sha256'] = hashlib.sha256((THRU / 'standards.ecsv').read_bytes()).hexdigest()
        entries['mosfire/throughput/standards.ecsv'] = idx
        print(f'flagged excluded_3mad in standards.ecsv: {excluded}')
    write_index(entries)
    print(f'index.yaml updated ({len(entries)} entr(ies))')
    return 0


if __name__ == '__main__':
    sys.exit(main())
