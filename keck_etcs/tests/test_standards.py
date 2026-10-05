"""A0V standards (design N3, D2; plan S15a): the J-scaled Vega model, classification, the driver's typing."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from astropy.table import Table

from keck_etcs.calib import harvest, standards

DRIVER = Path(__file__).resolve().parents[2] / 'scripts' / 'mosfire' / 'reduce_standard.py'
LDS749B = (323.06782305, 0.25447328)


@pytest.fixture(scope='module')
def driver():
    spec = importlib.util.spec_from_file_location('reduce_standard', DRIVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vega_synthetic_j_and_round_trip():
    jv = standards.vega_tmass_j()
    assert abs(jv - standards.TMASS_J_VEGA) < 0.05            # +0.024 photon-counting (see the module docstring)
    for j in (5.5, 9.0):
        w, f = standards.a0v_model(j)
        assert standards.synthetic_tmass_j(w, f) == pytest.approx(j, abs=1e-9)
        assert standards.v_equivalent(j) == pytest.approx(standards.VEGA_V + j - jv)


def test_model_equals_pypeit_vega_standard_at_v_equivalent():
    from pypeit.core.standard import VegaStandard
    j = 8.5
    s = VegaStandard(standards.v_equivalent(j))
    w, f = standards.a0v_model(j)
    pw, pf = np.asarray(s.wave, float).ravel(), np.asarray(s.flux, float).ravel()
    np.testing.assert_allclose(pf, np.interp(pw, w, f) * 1e17, rtol=1e-10)


def test_classify():
    a = standards.classify(*LDS749B)
    assert a['std_class'] == 'archive' and a['name'] == 'LDS749B' and a['archive'] == 'calspec'
    assert standards.classify(*LDS749B, std_class='A0V')['std_class'] == 'archive'   # a measured spectrum wins
    assert standards.classify(10.0, 10.0, std_class='A0V')['std_class'] == 'A0V'
    assert standards.classify(None, None, sptype='A0V')['std_class'] == 'A0V'
    assert standards.classify(10.0, 10.0)['std_class'] == 'unknown'


def test_sens_par_insertion():
    base = '# header\n[sensfunc]\n  algorithm = IR\n  [[IR]]\n    tell_npca = 3\n'
    text, rec = standards.write_sens_par(base, 7.25)
    lines = text.splitlines()
    i = lines.index('[sensfunc]')
    assert lines[i + 1] == '  star_type = A0' and lines[i + 2].startswith('  star_mag = ')
    assert float(lines[i + 2].split('=')[1]) == pytest.approx(rec['v_equivalent'], abs=1e-5)
    assert text.count('star_type') == 1 and '[[IR]]' in text


def test_harvest_std_class():
    assert harvest.std_class_of('lds749b_stisnic_008.fits.gz') == 'WD'
    assert harvest.std_class_of(None, {'j_2mass': 7.0}) == 'A0V'
    assert harvest.std_class_of(None) == 'unknown'
    assert harvest.std_class_of('vega_tspectool_vacuum.dat') == 'A0V'


def test_driver_frame_typing(driver):
    sky = {'AXESTAT': 'tracking', 'TARGNAME': 'HIP 12345', 'FLAMP1': 'off', 'FLAMP2': 'off'}
    std = {'std_class': 'A0V', 'ra': 50.0, 'dec': 20.0}
    assert driver.classify({**sky, 'PWSTATA7': 1}, 50.0, 20.0, std) == driver.LAMP_ARC
    assert driver.classify({**sky, 'FLAMP1': 'on'}, 50.0, 20.0, std) == 'pixelflat,illumflat,trace'
    assert driver.classify(sky, 50.0, 20.0 + 30 / 3600, std) == 'standard'
    assert driver.classify(sky, 50.0, 20.0 + 120 / 3600, std) == 'arc,science,tilt'
    assert driver.classify(sky, 50.0, 20.0, None) == 'arc,science,tilt'
    assert driver.classify(sky, *LDS749B, None) == 'standard'
    assert driver.separation_arcsec(10, 0, 10, 1 / 60) == pytest.approx(60.0, rel=1e-9)


def test_driver_long2pos_pairing_uses_pypeit(driver):
    t = Table({'filename': [f'f{i}.fits' for i in range(4)], 'frametype': ['standard'] * 4,
               'dithpat': ['long2pos'] * 4, 'dithpos': ['B', 'A', 'B', 'A'], 'dithoff': [-7.0, 7.0, -7.0, 7.0],
               'decker': ['long2pos'] * 4, 'mjd': [1.0, 2.0, 3.0, 4.0],
               'comb_id': [-1] * 4, 'bkg_id': [-1] * 4})
    notes = driver.pair_long2pos(t)
    assert notes == [] and 'setup' not in t.colnames
    assert list(t['comb_id']) == [1, 2, 3, 4]
    assert list(t['bkg_id']) == [2, 1, 4, 3]            # PypeIt's B-A pairs


def test_driver_reads_koa_frame_types(driver, tmp_path):
    from astropy.table import Table as T
    T(rows=[{'file': 'a.fits', 'frame_type': 'oh_arc'}, {'file': 'b.fits', 'frame_type': 'standard'}]).write(
        tmp_path / 'manifest.ecsv', format='ascii.ecsv')
    assert driver.raw_manifest_types(tmp_path) == {'a.fits': 'oh_arc', 'b.fits': 'standard'}
    assert driver.raw_manifest_types(tmp_path / 'none') == {}


def test_driver_flat_typing_without_flamp_cards(driver):
    old = {'AXESTAT': 'not controlling', 'TARGNAME': 'unknown', 'FLATSPEC': 1}
    assert driver.classify(old, 10.0, 10.0, None) == 'pixelflat,illumflat,trace'
    assert driver.classify({**old, 'FLATSPEC': 0}, 10.0, 10.0, None) == 'lampoffflats'
    assert driver.classify({'AXESTAT': 'tracking', 'TARGNAME': 'X', 'FLATSPEC': 1, 'FLAMP1': 'off',
                            'FLAMP2': 'off'}, 10.0, 10.0, None) == 'arc,science,tilt'   # 2022: FLATSPEC=1 on sky
