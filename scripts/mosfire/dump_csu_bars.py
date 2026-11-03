#!/usr/bin/env python
"""Print the CSU bar list (``Mechanical_Slit_List``) and the long2pos geometry of raw MOSFIRE frames.

Written for the S24b batch-1 sweep (2016-01-06 H: the bar carve of ``reduce_standard.py`` found no bar
inside the traced slits). For each frame: MASKNAME, CRPIX2, PSCALE, and the rows of ``Mechanical_Slit_List``
with the nominal spatial centre PypeIt's ``long2pos_match_bars`` assigns to each bar number
(``CRPIX2 + (23 - n) * pitch``). Run in ``pypeit14b``::

    conda run -n pypeit14b python scripts/mosfire/dump_csu_bars.py [--raw] FITS [FITS ...]

``--raw`` also prints the ASCII-table layout (``TBCOL``/``TFORM``) and the raw bytes of
``Mechanical_Slit_List`` (2016-01-06 H: the parsed columns are shifted).
"""
import sys

from astropy.io import fits
from pypeit.spectrographs.keck_mosfire import KeckMOSFIRESpectrograph as K


def main(files, raw=False):
    for f in files:
        with fits.open(f) as hdul:
            h = hdul[0].header
            ps, crpix2 = h['PSCALE'], float(h['CRPIX2'])
            gap = K._slit_gap(ps)
            pitch = K._CSUlength(ps) + gap
            print(f"{f}: MASKNAME={h.get('MASKNAME')!r} OBJECT={h.get('OBJECT')!r} CRPIX2={crpix2} PSCALE={ps} "
                  f"pitch={pitch:.2f} gap={gap:.2f} LONG2POS_POSB_BAR={K.LONG2POS_POSB_BAR}")
            names = [n for n in hdul if n.name.endswith('Slit_List')]
            for ext in names:
                d = hdul[ext.name].data
                print(f"  [{ext.name}] columns {d.columns.names}")
                if raw and ext.name == 'Mechanical_Slit_List':
                    hh = ext.header
                    print('   ', [(hh.get(f'TTYPE{i}'), hh.get(f'TBCOL{i}'), hh.get(f'TFORM{i}'))
                                  for i in range(1, hh['TFIELDS'] + 1)], 'NAXIS1', hh['NAXIS1'])
                    with open(f, 'rb') as fh:
                        fh.seek(ext._data_offset)
                        buf = fh.read(hh['NAXIS1'] * hh['NAXIS2'])
                    for i in range(hh['NAXIS2']):
                        print('    |' + buf[i * hh['NAXIS1']:(i + 1) * hh['NAXIS1']].decode('ascii', 'replace') + '|')
                for r in d:
                    cols = {c: r[c] for c in d.columns.names}
                    sn = str(cols.get('Slit_Number', '')).strip()
                    cen = f"  centre={crpix2 + (K.LONG2POS_POSB_BAR - int(sn)) * pitch:.1f}" if sn.isdigit() else ''
                    print('   ', cols, cen)


if __name__ == '__main__':
    args = sys.argv[1:]
    main([a for a in args if a != '--raw'], raw='--raw' in args)
