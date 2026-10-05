"""S11: the ETC against the measured S/N of J0841+3814 on 2022-04-09 (design 6.1, D18).

Slow: needs ``KECK_ETCS_DATA`` with the synced in-pod products of the night,
and PypeIt (``pypeit_flux_calib``, ``pypeit_coadd_1dspec``). Run with
``KECK_ETCS_DATA=... pytest -m slow --run-slow`` (``--run-slow`` is
pytest-astropy's switch, needed where that plugin is installed).
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'mosfire' / 'validate_j0841.py'

pytestmark = pytest.mark.slow


@pytest.fixture(scope='module')
def summary():
    if not os.environ.get('KECK_ETCS_DATA'):
        pytest.skip('KECK_ETCS_DATA is not set')
    from keck_etcs import paths
    night = paths.night_dir('mosfire', '20220409')
    if not (night / 'run_manifest.json').exists():
        pytest.skip(f'{night} has no synced products')
    spec = importlib.util.spec_from_file_location('validate_j0841', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    s = mod.main(redo=False, figure=False)
    s['_manifest'] = json.loads((night / 'run_manifest.json').read_text())
    return s


def test_d18_criterion(summary):
    r = summary['ratio_etc_over_measured']
    assert abs(r['band'] - 1) <= 0.20, r
    assert abs(r['interline'] - 1) <= 0.10, r


def test_signal_closure_and_n5(summary):
    assert abs(summary['signal_ratio_etc_over_measured'] - 1) <= 0.02
    assert abs(summary['n5_oh_centroid_offset_meas_minus_gemini']['median_offset_A']) < 0.5


def test_validated_against_in_pod_products(summary):
    p, m = summary['provenance'], summary['_manifest']
    assert p['image'] == m['image'] and p['image_digest'] == m['image_digest']
    assert p['pypeit_git_sha'] == p['pypeit_pin']
