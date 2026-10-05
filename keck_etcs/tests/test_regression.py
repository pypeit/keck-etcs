"""Frozen compute() outputs (design 6.2): fail on any relative change above 1e-6.

Regenerate only deliberately, with
``scripts/regen_regression_fixtures.py --regen --note "why"`` (adds a
CHANGES.md line).
"""
import json
from pathlib import Path

import pytest

from keck_etcs import etc
from keck_etcs.tests.regression import FIXTURES, compare, round_floats

DATA = Path(__file__).resolve().parent / 'data'
EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'


@pytest.mark.parametrize('name', sorted(FIXTURES))
def test_regression(name):
    ref = json.loads((DATA / f'reference_{name}.json').read_text())
    out = round_floats(etc.compute(ref['inputs']))
    diffs = compare(out, ref['output'])
    assert not diffs, f'{len(diffs)} difference(s), first: ' + '; '.join(diffs[:5])


@pytest.mark.parametrize('name', sorted(FIXTURES))
def test_fixture_inputs_are_the_examples(name):
    ref = json.loads((DATA / f'reference_{name}.json').read_text())
    assert ref['inputs'] == json.loads((EXAMPLES / f'{FIXTURES[name]}.json').read_text())


def test_compare_catches_small_changes():
    a = {'x': [1.0, 2.0], 'meta': {'keck_etcs_version': '1', 'era': 'e'}}
    assert compare(a, a) == []
    assert compare({**a, 'meta': {'keck_etcs_version': '2', 'era': 'e'}}, a) == []
    assert compare({**a, 'x': [1.0, 2.0 * (1 + 2e-6)]}, a)
    assert compare({**a, 'x': [1.0, 2.0 * (1 + 5e-7)]}, a) == []
