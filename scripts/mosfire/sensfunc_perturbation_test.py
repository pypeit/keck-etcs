#!/usr/bin/env python
"""How sensitive is the IR (telluric) sensfunc fit to tiny changes in its input? (S4b diagnosis)

Usage:
    conda run -n pypeit14b python scripts/mosfire/sensfunc_perturbation_test.py COADD
        [--levels 1e-5 1e-4 1e-3] [--n 3] [--sens FILE] [--outdir DIR]

Takes a coadded standard (``pypeit_coadd_1dspec`` output, HDU ``SPECTRUM``),
multiplies its ``flux`` by ``1 + level * N(0, 1)`` per pixel (fixed seeds),
refits with ``pypeit_sensfunc`` and the packaged ``.sens`` file, and compares
each zero point over 1.117-1.260 um with the fit to the unperturbed input
(``inspect_sensfunc.compare``). The fit is deterministic for a given input
(seed 777; ``compare_sensfunc_stacks.py``). This measures how much an
input difference far below the noise moves the result, i.e. the
reproducibility floor of the zero point between two reductions that are
numerically, but not bitwise, identical.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts' / 'mosfire'))
import inspect_sensfunc  # noqa: E402

DEFAULT_SENS = REPO / 'keck_etcs' / 'data' / 'pypeit_par' / 'keck_mosfire_J.sens'


def fit(spec, sens, out):
    with open(out.with_suffix('.log'), 'w') as f:
        rc = subprocess.run(['pypeit_sensfunc', str(spec), '-s', str(sens), '-o', str(out)],
                            stdout=f, stderr=subprocess.STDOUT, cwd=out.parent).returncode
    if rc != 0:
        raise SystemExit(f'pypeit_sensfunc failed on {spec}; see {out.with_suffix(".log")}')
    return out


def main(coadd, levels=(1e-5, 1e-4, 1e-3), n=3, sens=None, outdir=None):
    coadd = Path(coadd).resolve()
    sens = Path(sens or DEFAULT_SENS).resolve()
    outdir = Path(outdir or coadd.parent / 'perturbation_test').resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    base = inspect_sensfunc.load(fit(coadd, sens, outdir / 'sens_base.fits'))
    print(f'{"level":>8s} {"seed":>4s}  {"median":>9s} {"p05":>9s} {"p95":>9s} {"max|dev|":>9s}  median T')
    rows = []
    for level in levels:
        for seed in range(n):
            spec = outdir / f'coadd_{level:.0e}_{seed}.fits'
            with fits.open(coadd) as h:
                flux = h['SPECTRUM'].data['flux']
                rng = np.random.default_rng(1000 + seed)
                h['SPECTRUM'].data['flux'] = flux * (1 + level * rng.standard_normal(flux.size))
                h.writeto(spec, overwrite=True)
            out = fit(spec, sens, outdir / f'sens_{level:.0e}_{seed}.fits')
            c = inspect_sensfunc.compare(inspect_sensfunc.load(out), base)
            o, _ = inspect_sensfunc.inspect(out)
            rows.append((level, c))
            print(f'{level:8.0e} {seed:4d}  {c["median_ratio"]:9.5f} {c["p05"]:9.5f} {c["p95"]:9.5f} '
                  f'{c["max_abs_dev"]:9.5f}  {o["thru_median_window"]:.4f}', flush=True)
    for level in levels:
        devs = [max(abs(c['p05'] - 1), abs(c['p95'] - 1), abs(c['median_ratio'] - 1))
                for lv, c in rows if lv == level]
        print(f'level {level:.0e}: worst 5-95%/median deviation {max(devs):.4f} '
              f'(1% gate {"would FAIL" if max(devs) >= 0.01 else "passes"})')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('coadd')
    p.add_argument('--levels', nargs='+', type=float, default=[1e-5, 1e-4, 1e-3])
    p.add_argument('--n', type=int, default=3)
    p.add_argument('--sens')
    p.add_argument('--outdir')
    sys.exit(main(**vars(p.parse_args())))
