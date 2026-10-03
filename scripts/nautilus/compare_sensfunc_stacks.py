#!/usr/bin/env python
"""Is a sensfunc difference due to the software stack or to the inputs? (S4b diagnosis)

Usage:
    conda run -n pypeit14b python scripts/nautilus/compare_sensfunc_stacks.py SPEC1D
        [--image TAG] [--sens FILE] [--outdir DIR]

Runs ``pypeit_sensfunc`` with the same ``.sens`` file on the same input
spec1d (or coadd) three times: twice in the local environment and once inside
the container image (``docker run``, inputs mounted read-only). Then it
compares the zero points over 1.117-1.260 um with
``inspect_sensfunc.compare``: local-1 against local-2 (determinism) and
local-1 against the image (stack). It also prints the numpy, scipy and Python
versions on both sides.

Identical inputs giving identical local runs but a different image result
means the stack (Python, numpy, scipy, BLAS) moves the telluric fit. The
fit is ``scipy.optimize.differential_evolution`` with PypeIt's fixed seed
777. If the image agrees with local, the cause is in the inputs (the
spec1d).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts' / 'mosfire'))
import inspect_sensfunc  # noqa: E402

DEFAULT_IMAGE = 'gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.1'
DEFAULT_SENS = REPO / 'keck_etcs' / 'data' / 'pypeit_par' / 'keck_mosfire_J.sens'
VERSIONS = ("import sys, numpy, scipy, astropy, pypeit; "
            "print('python', sys.version.split()[0], '| numpy', numpy.__version__, '| scipy', "
            "scipy.__version__, '| astropy', astropy.__version__, '| pypeit', pypeit.__version__)")


def run(cmd, log):
    # run in the log's directory: pypeit_sensfunc writes sensfunc.par to its cwd
    with open(log, 'w') as f:
        rc = subprocess.run([str(c) for c in cmd], stdout=f, stderr=subprocess.STDOUT,
                            cwd=Path(log).parent).returncode
    if rc != 0:
        raise SystemExit(f'{cmd[0]} failed (exit {rc}); see {log}')


def main(spec1d, image=DEFAULT_IMAGE, sens=None, outdir=None):
    spec1d = Path(spec1d).resolve()
    sens = Path(sens or DEFAULT_SENS).resolve()
    outdir = Path(outdir or spec1d.parent / 'stack_test').resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    print('local :', subprocess.run([sys.executable, '-c', VERSIONS], capture_output=True,
                                    text=True).stdout.strip())
    print('image :', subprocess.run(['docker', 'run', '--rm', image, 'python', '-c', VERSIONS],
                                    capture_output=True, text=True).stdout.strip().splitlines()[-1])
    outs = {}
    for name in ('local1', 'local2'):
        out = outdir / f'sens_{name}.fits'
        run(['pypeit_sensfunc', spec1d, '-s', sens, '-o', out], outdir / f'{name}.log')
        outs[name] = out
    # In the image: inputs read-only at /in, outputs at /out. Run as root (as in a
    # pod; the image's cache is root-owned) and hand the outputs back to this user.
    out = outdir / 'sens_image.fits'
    cmd = (f'pypeit_sensfunc /in/{spec1d.name} -s /par/{sens.name} -o /out/{out.name}; '
           f'rc=$?; chown -R {os.getuid()}:{os.getgid()} /out; exit $rc')
    run(['docker', 'run', '--rm', '-v', f'{spec1d.parent}:/in:ro', '-v', f'{sens.parent}:/par:ro',
         '-v', f'{outdir}:/out', '-w', '/out', image, 'bash', '-lc', cmd], outdir / 'image.log')
    outs['image'] = out

    load = {k: inspect_sensfunc.load(v) for k, v in outs.items()}
    for a, b in (('local1', 'local2'), ('local1', 'image'), ('local2', 'image')):
        c = inspect_sensfunc.compare(load[a], load[b])
        print(f'{a:6s} / {b:6s}: median {c["median_ratio"]:.6f}, 5-95% {c["p05"]:.6f}-'
              f'{c["p95"]:.6f}, max |dev| {c["max_abs_dev"]:.6f}')
    for k, v in outs.items():
        o, _ = inspect_sensfunc.inspect(v)
        t = o['telluric']
        print(f'{k:6s}: median T {o["thru_median_window"]:.4f}, telluric R {t["resolution"]:.0f}, '
              f'chi2 {t["chi2"]:.1f}, niter {t["niter"]}, PCA {[round(x, 2) for x in t["pca_coeffs"]]}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('spec1d', help='Input spec1d or coadd file')
    p.add_argument('--image', default=DEFAULT_IMAGE)
    p.add_argument('--sens', help='.sens file (default: the packaged J file)')
    p.add_argument('--outdir', help='Output directory (default: <spec1d dir>/stack_test)')
    sys.exit(main(**vars(p.parse_args())))
