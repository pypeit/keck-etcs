#!/usr/bin/env python
"""Compare ``compute()`` outputs of this tree with those of an earlier release tree, field by field (plan S23b, design D49).

Usage:
    conda run -n pypeit14b python scripts/compare_release_outputs.py [--old DIR | --old-ref REF]
        [--rtol 1e-6] [--out TABLE.md] [--allow-string meta.calib_version ...] [-v]

Runs ``keck_etcs.etc.compute`` on every example (``examples/*.json``) and on
the inputs of every regression fixture (``keck_etcs/tests/data/reference_*.json``)
twice: in this working tree and in an **old** tree, a checkout or archive of
the previous release (``--old DIR``; or ``--old-ref REF``, default ``HEAD``,
which extracts ``git archive REF`` into a temporary directory, a read-only
git operation). Each run is a subprocess with the tree first on
``PYTHONPATH``, so the two never share a cached module or data file.

For every output field (top-level arrays and scalars, and the leaves of
``summary``, ``saturation`` and ``meta``) it reports the maximum relative
difference ``|new - old| / max(|new|, |old|)`` over the field's elements
(``0`` when both are zero; ``inf`` when only one is finite or the lengths
differ), as a Markdown table with one row per field and one column per
input. String fields show ``=`` or ``!=``; booleans and None likewise. An
input the old tree rejects (a band it did not have) is reported and
skipped.

Exit status 1 if any numeric field differs by more than ``--rtol``, or a
string field differs that is not in ``--allow-string`` (default
``meta.keck_etcs_version``, ``meta.calib_version`` and ``warnings``: a
release changes the tag by construction, and a warning may name a renamed
file). Allowed differences are still printed, element by element for a
list, so that a changed number inside a warning is seen.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ALLOW_STRINGS = ('meta.keck_etcs_version', 'meta.calib_version', 'warnings')
NESTED = ('meta', 'summary', 'saturation')

RUNNER = r'''
import json, sys, warnings
warnings.simplefilter("ignore")
from keck_etcs import etc
jobs = json.loads(open(sys.argv[1]).read())
out = {}
for name, inputs in jobs.items():
    try:
        out[name] = {"output": etc.compute(inputs)}
    except Exception as exc:
        out[name] = {"error": f"{type(exc).__name__}: {exc}"}
open(sys.argv[2], "w").write(json.dumps(out))
'''


def inputs_to_run():
    jobs = {}
    for f in sorted((REPO / 'examples').glob('*.json')):
        jobs[f'example:{f.stem}'] = json.loads(f.read_text())
    for f in sorted((REPO / 'keck_etcs' / 'tests' / 'data').glob('reference_*.json')):
        jobs[f'fixture:{f.stem[len("reference_"):]}'] = json.loads(f.read_text())['inputs']
    return jobs


def run_tree(tree, jobs, tmp):
    tree = Path(tree).resolve()
    jin, jout = tmp / f'{tree.name}_in.json', tmp / f'{tree.name}_out.json'
    jin.write_text(json.dumps(jobs))
    env = dict(os.environ)
    env['PYTHONPATH'] = str(tree) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    r = subprocess.run([sys.executable, '-c', RUNNER, str(jin), str(jout)], cwd=tree, env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'compute() runner failed in {tree}:\n{r.stderr}')
    res = json.loads(jout.read_text())
    # which keck_etcs the runner imported, for the report
    r = subprocess.run([sys.executable, '-c', 'import keck_etcs, sys; print(keck_etcs.__file__, keck_etcs.__version__)'],
                       cwd=tree, env=env, capture_output=True, text=True)
    return res, r.stdout.strip()


def leaves(out):
    """``{'field': value}`` with the nested dicts flattened one level ('summary.snr_pixel_median')."""
    flat = {}
    for k, v in out.items():
        if k in NESTED and isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, dict):            # meta.inputs: compared as one JSON string
                    flat[f'{k}.{kk}'] = json.dumps(vv, sort_keys=True)
                else:
                    flat[f'{k}.{kk}'] = vv
        else:
            flat[k] = v
    return flat


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def rel(a, b):
    if a is None and b is None:
        return 0.0
    if not (is_num(a) and is_num(b)):
        return math.inf
    if (math.isnan(a) and math.isnan(b)) or a == b:
        return 0.0
    if not (math.isfinite(a) and math.isfinite(b)):
        return math.inf
    return abs(a - b) / max(abs(a), abs(b))


def field_diff(new, old):
    """``(kind, value)``: ('num', max rel diff) or ('str', equal?)."""
    if isinstance(new, list) and isinstance(old, list):
        if len(new) != len(old):
            return 'num', math.inf
        if new and not all(is_num(x) or x is None for x in new):
            return 'str', new == old                 # warnings and other string lists
        return 'num', max((rel(a, b) for a, b in zip(new, old)), default=0.0)
    if is_num(new) and is_num(old):
        return 'num', rel(new, old)
    return 'str', new == old


def fmt(kind, v):
    if kind == 'str':
        return '=' if v else '!='
    return '0' if v == 0 else ('inf' if math.isinf(v) else f'{v:.1e}')


def main(old=None, old_ref='HEAD', rtol=1e-6, out=None, allow=ALLOW_STRINGS, verbose=False):
    jobs = inputs_to_run()
    with tempfile.TemporaryDirectory(prefix='keck_etcs_compare_') as tmpd:
        tmp = Path(tmpd)
        if old is None:
            old = tmp / 'old_release'
            old.mkdir()
            arch = subprocess.run(['git', 'archive', old_ref], cwd=REPO, capture_output=True)
            if arch.returncode != 0:
                print(f'git archive {old_ref} failed: {arch.stderr.decode()}')
                return 2
            subprocess.run(['tar', '-x', '-C', str(old)], input=arch.stdout, check=True)
            old_label = f'git archive {old_ref}'
        else:
            old_label = str(old)
        new_res, new_where = run_tree(REPO, jobs, tmp)
        old_res, old_where = run_tree(old, jobs, tmp)
    print(f'new: {new_where}\nold: {old_label} -> {old_where}')
    lines = [f'Inputs: {len(jobs)}; old tree: {old_label}; tolerance {rtol:g} relative.', '']
    skipped, fails = [], []
    names = [n for n in jobs if 'error' not in old_res[n] and 'error' not in new_res[n]]
    for n in jobs:
        if 'error' in new_res[n]:
            fails.append(f'{n}: compute() failed in this tree: {new_res[n]["error"]}')
        elif 'error' in old_res[n]:
            skipped.append(f'{n}: not in the old release ({old_res[n]["error"]})')
    flat_new = {n: leaves(new_res[n]['output']) for n in names}
    flat_old = {n: leaves(old_res[n]['output']) for n in names}
    fields = []
    for n in names:
        for k in list(flat_old[n]) + list(flat_new[n]):
            if k not in fields:
                fields.append(k)
    header = '| field | ' + ' | '.join(names) + ' |'
    lines += [header, '|' + '---|' * (len(names) + 1)]
    worst = {}
    for k in fields:
        cells = []
        for n in names:
            if k not in flat_old[n] or k not in flat_new[n]:
                cells.append('missing' if k not in flat_new[n] else 'new')
                fails.append(f'{n}: field {k} ' + ('missing in this tree' if k not in flat_new[n] else 'absent from the old release'))
                continue
            kind, v = field_diff(flat_new[n][k], flat_old[n][k])
            cells.append(fmt(kind, v))
            if kind == 'num':
                worst[k] = max(worst.get(k, 0.0), v)
                if v > rtol:
                    fails.append(f'{n}: {k} differs by {v:.2e} (> {rtol:g})')
            elif not v:
                a, b = flat_new[n][k], flat_old[n][k]
                if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                    what = '; '.join(f'[{i}] {x!r} (old {y!r})' for i, (x, y) in enumerate(zip(a, b)) if x != y)
                else:
                    what = f'{a!r} (old {b!r})'
                if k in allow:
                    cells[-1] = '!= (allowed)'
                    skipped.append(f'{n}: {k}: {what}, allowed')
                else:
                    fails.append(f'{n}: {k}: {what}')
        lines.append(f'| `{k}` | ' + ' | '.join(cells) + ' |')
    num = [v for v in worst.values() if math.isfinite(v)]
    lines += ['', f'Largest relative difference over every numeric field and input: '
                  f'{max(num) if num else 0:.2e}' + (' (inf for some field)' if any(math.isinf(v) for v in worst.values()) else '') + '.']
    for s in skipped:
        lines.append(f'- {s}')
    for f in fails:
        lines.append(f'- FAIL {f}')
    verdict = 'PASS: every numeric output agrees to ' + f'{rtol:g}' if not fails else f'FAIL ({len(fails)} difference(s))'
    lines += ['', verdict]
    text = '\n'.join(lines) + '\n'
    print(text)
    if out:
        Path(out).write_text(text)
        print(f'table written to {out}')
    return 1 if fails else 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--old', help='directory holding the old release tree (a checkout or git archive)')
    p.add_argument('--old-ref', default='HEAD', help='git ref to archive when --old is not given (default HEAD)')
    p.add_argument('--rtol', type=float, default=1e-6)
    p.add_argument('--out', help='write the Markdown table here too')
    p.add_argument('--allow-string', nargs='*', default=list(ALLOW_STRINGS),
                   help='string fields allowed to differ (default: the version tags)')
    p.add_argument('-v', '--verbose', action='store_true')
    a = p.parse_args()
    sys.exit(main(a.old, a.old_ref, a.rtol, a.out, tuple(a.allow_string), a.verbose))
