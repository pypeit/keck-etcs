#!/usr/bin/env python
"""Write the MOSFIRE detector table ``keck_etcs/data/mosfire/detector.ecsv`` (plan step S8, design 5.4, D12).

Usage:
    conda run -n pypeit14b python scripts/mosfire/build_detector_table.py

Columns ``n_reads`` and ``read_noise_e`` (e- rms per pixel per frame, the
Keck detector page values; CDS is ``n_reads = 1``) with the laboratory values
of Kulas et al. (2012) beside them for reference. ``meta`` holds the gain,
dark current, linearity limits, plate scales, minimum integration and the
source of each, as in design section 3. The ETC interpolates the read noise
linearly in log2(n_reads) (``keck_etcs.core.detector.read_noise``). The file
is registered in ``keck_etcs/data/index.yaml``.
"""
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table

import keck_etcs

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'detector.ecsv'
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
CALIB_VERSION = 'mosfire-J-2026.10-dev'
DETECTOR_PAGE = 'https://www2.keck.hawaii.edu/inst/mosfire/detector.html'

N_READS = [1, 4, 8, 16, 32, 64, 128]
RN_KECK = [21.0, 10.8, 7.7, 5.8, 4.2, 3.5, 3.0]           # Keck detector page
RN_LAB = [17.2, 8.9, 6.5, 4.9, 3.8, 3.3, np.nan]          # Kulas et al. 2012 (no 128-read value)


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    t = Table([N_READS, RN_KECK, RN_LAB], names=('n_reads', 'read_noise_e', 'read_noise_lab_e'))
    t['read_noise_lab_e'] = np.ma.masked_invalid(t['read_noise_lab_e'])
    t.meta = {
        'description': 'MOSFIRE H2RG detector: read noise per frame vs reads per group, and detector constants '
                       '(design section 3, D12)',
        'instrument': 'keck_mosfire',
        'read_noise_source': f'{DETECTOR_PAGE} (n_reads = 1 is CDS; MCDS-N for N >= 4)',
        'read_noise_lab_source': 'Kulas et al. 2012, SPIE 8453 (laboratory; for reference, not used)',
        'read_noise_interpolation': 'linear in log2(n_reads) (keck_etcs.core.detector.read_noise)',
        'gain_e_per_adu': 2.15, 'gain_source': f'{DETECTOR_PAGE}; header SYSGAIN',
        'dark_e_per_s_per_pix': 0.008, 'dark_source': f'{DETECTOR_PAGE} (< 0.008); PypeIt 28.8 e-/pix/hr',
        'linearity_adu': {'nonlinear_1pct': 26000, 'nonlinear_5pct': 37000, 'saturated': 43000},
        'linearity_e': {'nonlinear_1pct': 56000, 'nonlinear_5pct': 80000, 'saturated': 97000},
        'linearity_source': f'{DETECTOR_PAGE}; header SATURATE = 33000 noted but not used (D12)',
        'platescale_spatial_arcsec_per_pix': 0.1798, 'platescale_spatial_source': 'PypeIt keck_mosfire; header PSCALE 0.1799',
        'platescale_dispersion_arcsec_per_pix': 0.24,
        'platescale_dispersion_source': 'XTcalc; anamorphic factor 1.48 (header FCANAMOR)',
        'min_integration_s': 1.455, 'min_integration_source': f'{DETECTOR_PAGE}; header READTIME 1.45479 s',
        'n_pix': [2048, 2048], 'detector': 'Teledyne H2RG HgCdTe, 2.5 um cutoff',
        'persistence': '~0.04 percent, time constant ~600-660 s (not modeled)',
        'sampmode_codes': {1: 'Single', 2: 'CDS', 3: 'MCDS', 4: 'UTR'},
        'calib_version': CALIB_VERSION, 'keck_etcs_version': keck_etcs.__version__,
        'created': now, 'script': 'scripts/mosfire/build_detector_table.py',
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t.write(OUT, format='ascii.ecsv', overwrite=True)
    index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {})['mosfire/detector.ecsv'] = {
        'calib_version': CALIB_VERSION, 'created': now,
        'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'script': 'scripts/mosfire/build_detector_table.py',
        'provenance': f'Keck MOSFIRE detector page {DETECTOR_PAGE}: read noise vs reads, gain, dark, '
                      'linearity, minimum integration; plate scales from PypeIt and XTcalc'}
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))
    print(t)
    print(f'wrote {OUT.relative_to(REPO)}; index.yaml updated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
