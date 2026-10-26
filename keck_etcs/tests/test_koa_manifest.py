"""KOA census products and night manifests (plan S14)."""
import csv
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from astropy.table import Table

REPO = Path(__file__).resolve().parents[2]
CAND = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'koa_standards_candidates.ecsv'
MANIFESTS = REPO / 'nautilus' / 'manifests'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_candidate_table_has_the_dry_run_night():
    t = Table.read(CAND, format='ascii.ecsv')
    r = t[(t['night'] == '20220409') & (t['standard'] == 'LDS749B')][0]
    assert r['wide_slit'] and r['has_flats'] and r['std_class'] == 'WD' and r['public']
    assert 'MF.20220409.55932' in r['koaids'] and 'MF.20220409.56084' in r['koaids']
    assert set(t['std_class']) <= {'WD', 'archive', 'A0V', 'other'}
    a0v = t[t['std_class'] == 'A0V']
    assert np.all(np.isfinite(a0v['jmag_2mass']))


@pytest.mark.parametrize('name', ['nights_dryrun.csv', 'nights_pilot.csv'])
def test_manifests_parse_like_the_night_job(name):
    mm = load(REPO / 'scripts' / 'koa' / 'make_night_manifest.py', 'make_night_manifest')
    probs, n = mm.check(MANIFESTS / name)
    assert probs == [] and n >= 1
    rows = list(csv.DictReader(open(MANIFESTS / name)))
    assert list(rows[0])[:7] == list(mm.COLS)
    if name == 'nights_pilot.csv':
        assert 3 <= n <= 5 and '20220409' not in {r['night'] for r in rows}
        assert {'WD', 'A0V'} <= {r['std_class'] for r in rows}


def test_night_classes_and_slits():
    sm = load(REPO / 'scripts' / 'koa' / 'search_mosfire_standards.py', 'search_mosfire_standards')
    assert sm.night_of('2022-04-09 00:00:00', '15:32:12') == '20220409'
    assert sm.night_of('2022-04-08 00:00:00', '23:30:00') == '20220409'      # afternoon flats (13:30 HST)
    assert sm.slit_of('LONGSLIT-46x5') == (5.0, True)
    assert sm.slit_of('LONGSLIT-46x0.7') == (0.7, False)
    w, wide = sm.slit_of('long2pos_specphot (align)')
    assert np.isnan(w) and wide
    assert sm.slit_length_bars('LONGSLIT-3x4') == 3
    assert sm.is_dwarf_a0('A0V') and sm.is_dwarf_a0('A0') and sm.is_dwarf_a0('A0IV/V')
    assert not sm.is_dwarf_a0('A0III') and not sm.is_dwarf_a0('A1V')


def test_validation_targets_and_spec2d():
    v = Table.read(REPO / 'keck_etcs' / 'data' / 'mosfire' / 'koa_validation_targets.ecsv', format='ascii.ecsv')
    val = v[v['validation']]
    assert '20220409' in set(val['night']) and np.all(val['std_reducible'])
    mm = load(REPO / 'scripts' / 'koa' / 'make_night_manifest.py', 'make_night_manifest')
    probs, n = mm.check(MANIFESTS / 'nights_validation.csv')
    assert probs == [] and n == len(set(val['night']) - {'20220409'})
    vn = {r['night'] for r in csv.DictReader(open(MANIFESTS / 'nights_validation.csv'))}
    assert all(r['spec2d'] == '1' for r in csv.DictReader(open(MANIFESTS / 'nights_validation.csv')))
    for name in ('nights_batch1.csv', 'nights_pilot.csv'):
        for r in csv.DictReader(open(MANIFESTS / name)):
            assert (r['spec2d'] == '1') == (r['night'] in vn), (name, r['night'])
