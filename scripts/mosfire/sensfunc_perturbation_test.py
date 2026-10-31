#!/usr/bin/env python
"""How sensitive is the IR (telluric) sensfunc fit to tiny changes in its input, and which ``polyorder`` and ``tell_npca`` does a band need? (S4b diagnosis; S24a parameter test, design D53)

Usage:
    conda run -n pypeit14b python scripts/mosfire/sensfunc_perturbation_test.py COADD
        [--levels 1e-5 1e-4 1e-3] [--n 3] [--sens FILE] [--outdir DIR] [--band H]
        [--polyorders 4 5 6 8] [--tell-npca 2 3 4 5] [--jobs 4] [--json OUT.json]

**Perturbation test (S4b).** Takes a coadded standard
(``pypeit_coadd_1dspec`` output, HDU ``SPECTRUM``), multiplies its ``flux``
by ``1 + level * N(0, 1)`` per pixel (fixed seeds), refits with
``pypeit_sensfunc`` and the band's ``.sens`` file, and compares each zero
point over the analysis window with the fit to the unperturbed input
(``inspect_sensfunc.compare``). The fit is deterministic for a given input
(seed 777; ``compare_sensfunc_stacks.py``). This measures how much an
input difference far below the noise moves the result, i.e. the
reproducibility floor of the zero point between two reductions that are
numerically, but not bitwise, identical. The window is the J2 analysis
window (1.117-1.260 um) without ``--band``, and the band's common window
(``Band.common_window_A``) with it.

**Parameter test (S24a, D53).** With ``--polyorders`` the script loops over
``polyorder`` (the ``.sens`` file's value replaced in a copy), fitting the
unperturbed coadd and ``--n`` perturbations at the first ``--levels`` value
(1e-5 by default) for each order, and reports per order:

- ``stability``: the worst deviation of the perturbed zero points from the
  unperturbed one over the window (the larger of ``|median - 1|``,
  ``|p05 - 1|``, ``|p95 - 1|`` of the ratio, over the seeds), the S4b
  metric; threshold **1 percent**;
- ``next_rms`` and ``next_max``: rms and maximum of ``ratio - 1`` between this
  order's zero point and the **next order up** over the window; threshold
  **1 percent** rms;
- ``edge_rms`` and ``edge_max``: the same within 100 A of the two edges
  of the window, inside it (where an underfit shows first; the filter
  edges outside the common window are the combine edge trim's business,
  D53); threshold **2 percent** rms.

The chosen order is the **lowest that passes all three**; the highest order
tried has no next order and cannot be chosen by the test (it is the
reference for the one below). With ``--tell-npca`` the same loop then runs
over ``tell_npca`` at the chosen order (its next-value difference against
the next ``tell_npca`` up), and the lowest passing value is chosen. The
tables are printed, written to ``--json`` with every number, and the
summary lines are in the form the band's ``.sens`` header quotes (D53).
``--jobs`` runs that many ``pypeit_sensfunc`` processes at once (each is
about one core). A fit whose output already exists in ``--outdir`` is
reused, so an interrupted run resumes; use a fresh ``--outdir`` for a new
``.sens`` baseline.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from astropy.io import fits

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts' / 'mosfire'))
import inspect_sensfunc  # noqa: E402

DEFAULT_SENS = REPO / 'keck_etcs' / 'data' / 'pypeit_par' / 'keck_mosfire_J.sens'
STABILITY_MAX = 0.01       # D53 (a): 1e-5 perturbation stability below 1 percent
NEXT_RMS_MAX = 0.01        # D53 (b): rms difference to the next order up over the common window
EDGE_RMS_MAX = 0.02        # D53 (b): the same within EDGE_A of the window's edges (inside the window)
EDGE_A = 100.0


def fit(spec, sens, out):
    """Run ``pypeit_sensfunc``; return the output path (the fit is skipped when it exists)."""
    if out.exists():
        return out
    with open(out.with_suffix('.log'), 'w') as f:
        rc = subprocess.run(['pypeit_sensfunc', str(spec), '-s', str(sens), '-o', str(out)],
                            stdout=f, stderr=subprocess.STDOUT, cwd=out.parent).returncode
    if rc != 0 or not out.exists():
        raise SystemExit(f'pypeit_sensfunc failed on {spec}; see {out.with_suffix(".log")}')
    return out


def perturbed_coadds(coadd, outdir, level, n):
    """The ``n`` perturbed copies of the coadd at ``level`` (fixed seeds), written once."""
    specs = []
    for seed in range(n):
        spec = outdir / f'coadd_{level:.0e}_{seed}.fits'
        if not spec.exists():
            with fits.open(coadd) as h:
                flux = h['SPECTRUM'].data['flux']
                rng = np.random.default_rng(1000 + seed)
                h['SPECTRUM'].data['flux'] = flux * (1 + level * rng.standard_normal(flux.size))
                h.writeto(spec, overwrite=True)
        specs.append(spec)
    return specs


def sens_variant(base_text, outdir, polyorder=None, tell_npca=None):
    """A copy of the ``.sens`` file with ``polyorder`` and/or ``tell_npca`` replaced."""
    text = base_text
    tag = []
    if polyorder is not None:
        text, k = re.subn(r'(?m)^(\s*polyorder\s*=\s*)\S+', rf'\g<1>{int(polyorder)}', text)
        if k == 0:
            text = text.replace('[sensfunc]\n', f'[sensfunc]\n  polyorder = {int(polyorder)}\n', 1)
        tag.append(f'p{int(polyorder)}')
    if tell_npca is not None:
        text, k = re.subn(r'(?m)^(\s*tell_npca\s*=\s*)\S+', rf'\g<1>{int(tell_npca)}', text)
        if k == 0:
            text = text.replace('[[IR]]\n', f'[[IR]]\n    tell_npca = {int(tell_npca)}\n', 1)
        tag.append(f'n{int(tell_npca)}')
    path = outdir / f'sens_{"_".join(tag) or "base"}.sens'
    path.write_text(text)
    return path, '_'.join(tag)


def stability(base, others, window):
    """Worst deviation of the perturbed zero points from the unperturbed one over ``window`` (S4b metric)."""
    devs = []
    for o in others:
        c = inspect_sensfunc.compare(o, base, window)
        devs.append(max(abs(c['p05'] - 1), abs(c['p95'] - 1), abs(c['median_ratio'] - 1)))
    return float(max(devs)) if devs else None


def diff_stats(a, b, window):
    """rms and max of ``ratio - 1`` between two zero points over ``window`` (``a`` on its own grid, ``b`` interpolated)."""
    (_, wa, za), (_, wb, zb) = a, b
    ga, gb = inspect_sensfunc.good_zp(wa, za), inspect_sensfunc.good_zp(wb, zb)
    sel = ga & (wa >= window[0]) & (wa <= window[1]) & (wa >= wb[gb].min()) & (wa <= wb[gb].max())
    if not sel.any():
        return {'n': 0, 'rms': None, 'max': None}
    r = 10 ** (0.4 * (za[sel] - np.interp(wa[sel], wb[gb], zb[gb]))) - 1
    return {'n': int(sel.sum()), 'rms': float(np.sqrt(np.mean(r ** 2))), 'max': float(np.max(np.abs(r)))}


def edge_windows(window):
    """The two EDGE_A-wide zones just inside the edges of the analysis window."""
    lo, hi = float(window[0]), float(window[1])
    return (lo, lo + EDGE_A), (hi - EDGE_A, hi)


def edge_stats(a, b, window):
    """``diff_stats`` over both edge zones of ``window`` together (rms over the union, max over both)."""
    w1, w2 = edge_windows(window)
    d1, d2 = diff_stats(a, b, w1), diff_stats(a, b, w2)
    n = d1['n'] + d2['n']
    if n == 0:
        return {'n': 0, 'rms': None, 'max': None, 'windows_A': [list(w1), list(w2)]}
    rms = float(np.sqrt((d1['n'] * (d1['rms'] or 0) ** 2 + d2['n'] * (d2['rms'] or 0) ** 2) / n))
    return {'n': n, 'rms': rms, 'max': float(max(d1['max'] or 0, d2['max'] or 0)),
            'windows_A': [[float(w1[0]), float(w1[1])], [float(w2[0]), float(w2[1])]]}


def parameter_loop(name, values, coadd, specs, base_text, outdir, window, band, jobs, fixed=None):
    """Fit every value of one parameter (``polyorder`` or ``tell_npca``) on the coadd and its perturbations;
    return the per-value rows and the chosen value (the lowest passing D53)."""
    fixed = fixed or {}
    plan = []
    for v in values:
        kw = dict(fixed, **{name: v})
        par, tag = sens_variant(base_text, outdir, **kw)
        plan.append((v, tag, par, [(coadd, outdir / f'sens_{tag}_base.fits')]
                     + [(s, outdir / f'sens_{tag}_{s.stem.split("_", 1)[1]}.fits') for s in specs]))
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        list(ex.map(lambda job: fit(*job), [(spec, par, out) for _, _, par, fits_ in plan for spec, out in fits_]))
    loaded = {}
    for v, tag, par, fits_ in plan:
        loaded[v] = [inspect_sensfunc.load(out) for _, out in fits_]
    rows = []
    for i, (v, tag, par, fits_) in enumerate(plan):
        base, others = loaded[v][0], loaded[v][1:]
        o, _ = inspect_sensfunc.inspect(fits_[0][1], window, band)
        row = {name: v, 'stability': stability(base, others, window), 'thru_median_window': o['thru_median_window'],
               'zp_range_A': o['zp_range_A'], 'telluric_chi2': (o.get('telluric') or {}).get('chi2'),
               'telluric_success': (o.get('telluric') or {}).get('success'), 'next': None, 'edge': None, 'files': {
                   'base': str(fits_[0][1].name), 'perturbed': [str(f.name) for _, f in fits_[1:]], 'sens': par.name}}
        if i + 1 < len(plan):
            nxt = loaded[plan[i + 1][0]][0]
            row['next_value'] = plan[i + 1][0]
            row['next'] = diff_stats(base, nxt, window)
            row['edge'] = edge_stats(base, nxt, window)
        row['pass'] = bool(row['stability'] is not None and row['stability'] < STABILITY_MAX
                           and row['next'] is not None and row['next']['rms'] is not None and row['next']['rms'] < NEXT_RMS_MAX
                           and row['edge'] is not None and row['edge']['rms'] is not None and row['edge']['rms'] < EDGE_RMS_MAX)
        rows.append(row)
    chosen = next((r[name] for r in rows if r['pass']), None)
    return rows, chosen


def table_lines(name, rows, chosen, window):
    f = lambda x, s=4: '    -   ' if x is None else f'{x:8.{s}f}'
    out = [f'{name:>10s} {"stability":>9s} {"next":>5s} {"next_rms":>9s} {"next_max":>9s} {"edge_rms":>9s} {"edge_max":>9s} '
           f'{"thru_med":>9s} {"chi2":>8s}  pass']
    for r in rows:
        nx = r['next'] or {}
        ed = r['edge'] or {}
        out.append(f"{r[name]:>10d} {f(r['stability'])} {str(r.get('next_value', '-')):>5s} {f(nx.get('rms'))} "
                   f"{f(nx.get('max'))} {f(ed.get('rms'))} {f(ed.get('max'))} {f(r['thru_median_window'])} "
                   f"{f(r['telluric_chi2'], 2)}  {'PASS' if r['pass'] else ('-' if r['next'] is None else 'FAIL')}")
    out.append(f'{name}: chosen {chosen} (lowest value with stability < {STABILITY_MAX:.0%}, rms to the next value up '
               f'< {NEXT_RMS_MAX:.0%} over {window[0]:.0f}-{window[1]:.0f} A and < {EDGE_RMS_MAX:.0%} within '
               f'{EDGE_A:.0f} A of the edges)' if chosen is not None else
               f'{name}: NO value passes; the highest value tried is the reference only')
    return out


def main(coadd, levels=(1e-5, 1e-4, 1e-3), n=3, sens=None, outdir=None, band=None, polyorders=None,
         tell_npca=None, jobs=4, json_out=None):
    coadd = Path(coadd).resolve()
    sens = Path(sens or DEFAULT_SENS).resolve()
    outdir = Path(outdir or coadd.parent / 'perturbation_test').resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    window = inspect_sensfunc.JWIN
    if band:
        from keck_etcs.instruments.mosfire import MOSFIRE
        window = tuple(float(x) for x in MOSFIRE.bands[str(band)].common_window_A)
    summary = {'coadd': str(coadd), 'sens': str(sens), 'band': band, 'window_A': list(window), 'levels': list(levels),
               'n': n, 'thresholds': {'stability': STABILITY_MAX, 'next_rms': NEXT_RMS_MAX, 'edge_rms': EDGE_RMS_MAX,
                                      'edge_A': EDGE_A},
               'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'script': 'scripts/mosfire/sensfunc_perturbation_test.py'}
    if not polyorders and not tell_npca:
        base = inspect_sensfunc.load(fit(coadd, sens, outdir / 'sens_base.fits'))
        print(f'{"level":>8s} {"seed":>4s}  {"median":>9s} {"p05":>9s} {"p95":>9s} {"max|dev|":>9s}  median T')
        rows = []
        for level in levels:
            for seed in range(n):
                spec = perturbed_coadds(coadd, outdir, level, seed + 1)[-1]
                out = fit(spec, sens, outdir / f'sens_{level:.0e}_{seed}.fits')
                c = inspect_sensfunc.compare(inspect_sensfunc.load(out), base, window)
                o, _ = inspect_sensfunc.inspect(out, window, band)
                rows.append((level, c))
                print(f'{level:8.0e} {seed:4d}  {c["median_ratio"]:9.5f} {c["p05"]:9.5f} {c["p95"]:9.5f} '
                      f'{c["max_abs_dev"]:9.5f}  {o["thru_median_window"]:.4f}', flush=True)
        worst = {}
        for level in levels:
            devs = [max(abs(c['p05'] - 1), abs(c['p95'] - 1), abs(c['median_ratio'] - 1))
                    for lv, c in rows if lv == level]
            worst[f'{level:.0e}'] = max(devs)
            print(f'level {level:.0e}: worst 5-95%/median deviation {max(devs):.4f} '
                  f'(1% gate {"would FAIL" if max(devs) >= 0.01 else "passes"})')
        summary['worst_by_level'] = worst
        if json_out:
            Path(json_out).write_text(json.dumps(summary, indent=1) + '\n')
        return 0

    # the D53 parameter test
    level = float(levels[0])
    specs = perturbed_coadds(coadd, outdir, level, n)
    base_text = sens.read_text()
    print(f'{coadd.name}: band {band}, window {window[0]:.0f}-{window[1]:.0f} A, perturbation {level:.0e} x {n}, '
          f'{sens.name}; outputs in {outdir}')
    chosen_p = None
    if polyorders:
        rows, chosen_p = parameter_loop('polyorder', [int(v) for v in polyorders], coadd, specs, base_text, outdir,
                                        window, band, jobs)
        lines = table_lines('polyorder', rows, chosen_p, window)
        print('\n'.join(lines), flush=True)
        summary['polyorder'] = {'values': [int(v) for v in polyorders], 'rows': rows, 'chosen': chosen_p, 'table': lines}
    if tell_npca:
        fixed = {'polyorder': chosen_p} if chosen_p is not None else {}
        if polyorders and chosen_p is None:
            print('tell_npca loop at the .sens file\'s polyorder (no order passed)')
        rows, chosen_n = parameter_loop('tell_npca', [int(v) for v in tell_npca], coadd, specs, base_text, outdir,
                                        window, band, jobs, fixed=fixed)
        lines = table_lines('tell_npca', rows, chosen_n, window)
        print('\n'.join(lines), flush=True)
        summary['tell_npca'] = {'values': [int(v) for v in tell_npca], 'rows': rows, 'chosen': chosen_n,
                                'at_polyorder': fixed.get('polyorder'), 'table': lines}
    if json_out:
        Path(json_out).write_text(json.dumps(summary, indent=1) + '\n')
        print(f'written {json_out}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('coadd')
    p.add_argument('--levels', nargs='+', type=float, default=[1e-5, 1e-4, 1e-3])
    p.add_argument('--n', type=int, default=3)
    p.add_argument('--sens')
    p.add_argument('--outdir')
    p.add_argument('--band', help='band: its common window is the analysis window (default: the J2 window)')
    p.add_argument('--polyorders', nargs='+', type=int, help='D53: loop over polyorder, e.g. 4 5 6 8')
    p.add_argument('--tell-npca', nargs='+', type=int, dest='tell_npca', help='D53: loop over tell_npca, e.g. 2 3 4 5')
    p.add_argument('--jobs', type=int, default=4, help='parallel pypeit_sensfunc processes')
    p.add_argument('--json', dest='json_out')
    sys.exit(main(**vars(p.parse_args())))
