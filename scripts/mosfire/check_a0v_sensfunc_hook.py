#!/usr/bin/env python
"""Exercise the A0V sensfunc path end to end on an existing coadd (plan S15a; mechanics only).

Usage:
    conda run -n pypeit14b python scripts/mosfire/check_a0v_sensfunc_hook.py [--date 20220409] [--out DIR]

No A0V night is reduced yet, so this runs ``pypeit_sensfunc`` on the night's
standard coadd (``sens/spec1d_coadd_*.fits``, LDS749B on 2022-04-09) with the
A0V ``.sens`` file that ``build_sensfunc.py`` writes
(``keck_etcs.calib.standards.write_sens_par``), at two 2MASS J magnitudes
one magnitude apart. LDS749B is a white dwarf, so the zero points are
physically meaningless; what is checked is the machinery:

- PypeIt accepts ``star_type = A0`` / ``star_mag = V_eq`` and builds a sensfunc;
- the zero point rises by 1 mag (to 0.5 percent; the IR telluric refit is
  not exactly linear) between the two runs, since a fainter assumed star
  means a more sensitive instrument;
- PypeIt records ``std_cal = None`` for a model standard, so the class comes
  from the model record: ``keck_etcs.calib.harvest.std_class_of(std_cal,
  model)`` must read A0V with it and ``unknown`` (never WD) without it.

Outputs go to ``--out`` (default ``<night>/a0v_hook_check/``), never into
``sens/``.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

from keck_etcs import paths
from keck_etcs.calib import harvest, standards

REPO = Path(__file__).resolve().parents[2]
SENS = REPO / 'keck_etcs' / 'data' / 'pypeit_par' / 'keck_mosfire_J.sens'


def main(date='20220409', out=None):
    night = paths.night_dir('mosfire', date)
    coadd = sorted((night / 'sens').glob('spec1d_coadd_*.fits'))[0]
    out = Path(out) if out else night / 'a0v_hook_check'
    out.mkdir(parents=True, exist_ok=True)
    from pypeit.sensfunc import SensFunc
    res = {}
    for j in (15.0, 16.0):
        text, rec = standards.write_sens_par(SENS.read_text(), j)
        par = out / f'a0v_J{j:.1f}.sens'
        par.write_text(text)
        sf = out / f'sens_a0v_J{j:.1f}.fits'
        with open(out / f'sens_a0v_J{j:.1f}.log', 'w') as log:
            rc = subprocess.run(['pypeit_sensfunc', str(coadd), '-s', str(par), '-o', str(sf)], stdout=log,
                                stderr=subprocess.STDOUT, cwd=out).returncode
        if rc != 0 or not sf.exists():
            print(f'J = {j}: pypeit_sensfunc failed (exit {rc}); see {out}/sens_a0v_J{j:.1f}.log')
            return 1
        s = SensFunc.from_file(str(sf), chk_version=False)
        w = np.asarray(s.sens['SENS_WAVE'][0], float)
        zp = np.asarray(s.sens['SENS_ZEROPOINT'][0], float)
        good = (w > 11700) & (w < 12400) & np.isfinite(zp) & (zp > 0)
        res[j] = {'v_eq': rec['v_equivalent'], 'std_cal': str(s.std_cal), 'zp': float(np.median(zp[good]))}
        res[j]['class_with'] = harvest.std_class_of(s.std_cal, rec)
        res[j]['class_without'] = harvest.std_class_of(s.std_cal)
        print(f"J = {j}: V_eq {rec['v_equivalent']}, std_cal {s.std_cal!r} -> std_class with the model record "
              f"{res[j]['class_with']}, without {res[j]['class_without']}; median ZP 1.17-1.24 um {res[j]['zp']:.4f}")
    dz = res[16.0]['zp'] - res[15.0]['zp']
    ok = (abs(dz - 1.0) < 5e-3 and all(r['class_with'] == 'A0V' for r in res.values())
          and all(r['class_without'] == 'unknown' for r in res.values()))
    print(f'zero-point shift for +1 mag in J: {dz:+.4f} (expected +1.000 to 0.5%); classes ok: '
          f"{all(r['class_with'] == 'A0V' and r['class_without'] == 'unknown' for r in res.values())} -> "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--date', default='20220409')
    p.add_argument('--out')
    a = p.parse_args()
    sys.exit(main(a.date, a.out))
