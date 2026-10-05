#!/usr/bin/env python
"""Compare, or deliberately regenerate, the ETC regression fixtures (design 6.2, plan S9).

Usage:
    conda run -n pypeit14b python scripts/regen_regression_fixtures.py             # report differences only
    conda run -n pypeit14b python scripts/regen_regression_fixtures.py --regen --note "why"

Each fixture ``keck_etcs/tests/data/reference_<name>.json`` holds ``inputs``
(a copy of ``examples/<example>.json``) and ``output`` (``compute`` of it,
floats rounded to 10 significant digits). ``keck_etcs/tests/test_regression.py``
fails on any relative change above 1e-6. Regeneration is never automatic:
``--regen`` needs ``--note``, which is appended to ``CHANGES.md`` with the
date, the keck_etcs version and the throughput ``calib_version`` the
fixtures were frozen against.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from keck_etcs import etc  # noqa: E402
from keck_etcs.tests.regression import FIXTURES, compare, round_floats  # noqa: E402

CHANGES = REPO / 'CHANGES.md'


def main(regen=False, note=None):
    if regen and not note:
        print('--regen needs --note "reason" (it goes into CHANGES.md)')
        return 2
    n_diff, calib = 0, set()
    for name, example in FIXTURES.items():
        fixture = REPO / 'keck_etcs' / 'tests' / 'data' / f'reference_{name}.json'
        inputs = json.loads((REPO / 'examples' / f'{example}.json').read_text())
        output = round_floats(etc.compute(inputs))
        calib.add(output['meta']['calib_version'])
        if fixture.exists():
            old = json.loads(fixture.read_text())
            diffs = compare(output, old['output'])
            if old['inputs'] != inputs:
                diffs.insert(0, 'inputs differ from the example')
        else:
            diffs = ['no fixture yet']
        n_diff += bool(diffs)
        print(f'{name} ({example}.json): ' + ('unchanged' if not diffs else f'{len(diffs)} difference(s)'))
        for d in diffs[:10]:
            print(f'    {d}')
        if regen:
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text(json.dumps({'inputs': inputs, 'output': output}, indent=1) + '\n')
    if regen:
        import keck_etcs
        day = datetime.date.today().isoformat()
        line = (f'- {day}: regression fixtures regenerated (keck_etcs {keck_etcs.__version__}, throughput '
                f'{", ".join(sorted(calib))}): {note}\n')
        text = CHANGES.read_text() if CHANGES.exists() else '# Changes\n'
        head = '## Regression fixtures\n'
        if head not in text:
            text = text.rstrip('\n') + '\n\n' + head + '\n'
        CHANGES.write_text(text.replace(head + '\n', head + '\n' + line, 1) if head + '\n' in text
                           else text + line)
        print(f'regenerated {len(FIXTURES)} fixtures; CHANGES.md: {line.strip()}')
    return 0 if (regen or n_diff == 0) else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--regen', action='store_true', help='overwrite the fixtures (deliberate)')
    p.add_argument('--note', help='reason for regenerating; appended to CHANGES.md')
    a = p.parse_args()
    sys.exit(main(a.regen, a.note))
