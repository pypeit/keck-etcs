"""A0V standards (design N3, D2; plan S15a): the J-scaled Vega model, classification, the driver's typing.

Every test here reaches PypeIt (its Vega spectrum, 2MASS J response, standard-star archive or the
``reduce_standard.py`` driver, which imports it), so the whole module is skipped where PypeIt is not
installed: the ``etc`` CI job and a plain ``pip install .[test]``. The ``calib`` CI job runs it.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from astropy.table import Table

pytest.importorskip('pypeit')

from keck_etcs.calib import harvest, standards  # noqa: E402

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
        w, f = standards.a0v_model('J', j)
        assert standards.synthetic_tmass_j(w, f) == pytest.approx(j, abs=1e-9)
        assert standards.v_equivalent(j) == pytest.approx(standards.VEGA_V + j - jv)


def test_model_equals_pypeit_vega_standard_at_v_equivalent():
    from pypeit.core.standard import VegaStandard
    j = 8.5
    s = VegaStandard(standards.v_equivalent(j))
    w, f = standards.a0v_model('J', j)
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


def test_a0v_model_per_band_round_trip():
    """D51: the model is scaled in the band's own 2MASS band; Y/J/J2 in J, H in H, K in Ks."""
    assert [standards.tmass_band(b) for b in ('Y', 'J', 'J2', 'J3', 'H', 'K')] == ['J', 'J', 'J', 'J', 'H', 'K']
    for tb in ('J', 'H', 'K'):
        assert abs(standards.vega_tmass(tb) - standards.TMASS[tb]['vega_mag']) < 0.06, tb
    for band, m in (('H', 7.0), ('K', 6.5), ('Y', 8.0)):
        w, f = standards.a0v_model(band, m)
        assert standards.synthetic_tmass(w, f, standards.tmass_band(band)) == pytest.approx(m, abs=1e-9)
        assert standards.v_equivalent(m, band) == pytest.approx(
            standards.VEGA_V + m - standards.vega_tmass(standards.tmass_band(band)))
    assert standards.jhk_offset_mag('J', 7.0, 7.0) == 0.0
    # an A0V star has Vega's colours: scaling in H or Ks then equals scaling in J to within the colour error
    jv, hv_, kv = (standards.vega_tmass(b) for b in ('J', 'H', 'K'))
    assert standards.jhk_offset_mag('H', 7.0 + (hv_ - jv), 7.0) == pytest.approx(0.0, abs=1e-9)
    text, rec = standards.write_sens_par('[sensfunc]\n', 7.0, band='K', j_mag=7.3)
    assert rec['band_2mass'] == 'K' and rec['a0v_scaled_to'] == '2MASS K' and rec['mag_2mass'] == 7.0
    assert rec['j_2mass'] == 7.3 and rec['a0v_jhk_offset_mag'] == pytest.approx((7.0 - kv) - (7.3 - jv), abs=1e-4)
    assert '2MASS K = 7.0' in text and f"star_mag = {rec['v_equivalent']:.5f}" in text
    _, rj = standards.sens_par_lines(7.0)
    assert rj['band_2mass'] == 'J' and rj['j_2mass'] == 7.0 and rj['a0v_jhk_offset_mag'] == 0.0


def test_band_magnitude_column_and_env(monkeypatch):
    """S24a: the A0V model takes the band's own 2MASS magnitude from the manifest column of that band (D51)."""
    assert [standards.mag_column(b) for b in ('Y', 'J', 'J2', 'H', 'K')] == \
        ['jmag_2mass', 'jmag_2mass', 'jmag_2mass', 'hmag_2mass', 'kmag_2mass']
    env = {'JMAG_2MASS': '6.142', 'HMAG_2MASS': '6.163', 'KMAG_2MASS': ''}
    assert standards.mag_from_env('H', env) == 6.163 and standards.mag_from_env('J', env) == 6.142
    assert standards.mag_from_env('K', env) is None and standards.mag_from_env('Y', {}) is None


def test_driver_standard_record_uses_the_band_magnitude(driver, monkeypatch):
    """The driver's record: --mag, else the band's column, else J for the J group; H and K keep J as the cross-check."""
    import types
    for k in ('STANDARD', 'STD_RA', 'STD_DEC', 'STD_CLASS', 'JMAG_2MASS', 'HMAG_2MASS', 'KMAG_2MASS'):
        monkeypatch.delenv(k, raising=False)
    args = types.SimpleNamespace(std_name='HD79108', std_ra='138.05367', std_dec='3.866978', std_class='A0V',
                                 jmag='6.142', mag=None)
    monkeypatch.setenv('HMAG_2MASS', '6.163')
    rec = driver.standard_record(args, 'H')
    assert rec['std_class'] == 'A0V' and rec['mag_2mass'] == 6.163 and rec['mag_band_2mass'] == 'H'
    assert rec['jmag_2mass'] == 6.142
    rec = driver.standard_record(args, 'J')
    assert rec['mag_2mass'] == 6.142 and rec['mag_band_2mass'] == 'J'
    args.mag = '6.2'
    assert driver.standard_record(args, 'K')['mag_2mass'] == 6.2
    args.mag = None
    with pytest.raises(driver.StageError):
        driver.standard_record(args, 'K')                # no --mag, no $KMAG_2MASS


@pytest.fixture(scope='module')
def builder():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'mosfire' / 'build_sensfunc.py'
    spec = importlib.util.spec_from_file_location('build_sensfunc', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_sensfunc_edge_mask_and_resolution_guess(builder):
    """S24a (D53): the filter-edge mask window and the telluric resolution guess for Y, H and K; J untouched."""
    lo, hi = builder.filter_window('H')
    assert 14600 < lo < 14700 and 18000 < hi < 18150            # the H filter's half-maximum points
    assert builder.filter_window('H', 0.9)[0] > lo
    r07, fwhm07, src = builder.resln_guess('H', 0.7)
    r4, fwhm4, _ = builder.resln_guess('H', 4.0)
    assert 3500 < r07 < 4500 and fwhm07 == pytest.approx(2.5597, abs=1e-3)      # the measured 0.7" row
    assert r4 < r07 / 4 and src.startswith('measured')
    assert builder.EDGE_GROUPS == ('Y', 'H', 'K') and builder.FILTER_MASK_FRAC == 0.5
    text = '[sensfunc]\n  polyorder = 5\n  [[IR]]\n    tell_npca = 3\n'
    out = builder.with_resln(text, {'resln_guess': {'value': 1560.4}})
    assert '    resln_frac_bounds = 0.4, 1.5\n    resln_guess = 1560.4\n    tell_npca = 3' in out
    assert builder.with_resln(text, {'resln_guess': None}) == text
    assert 'resln_guess = 900.0' in builder.with_resln(out, {'resln_guess': {'value': 900.0}})
    man = {'specphot': {'bars': [{'spat_id': 946, 'width_arcsec': 4.0}, {'spat_id': 990, 'width_arcsec': 0.7}]},
           'frames': [{'filename': 'a.fits', 'maskname': 'LONGSLIT-3x0.7'}]}
    assert builder.slit_width_of(man, {'slit': 946, 'frame': 'a.fits'}) == 4.0
    assert builder.slit_width_of(man, {'slit': 1, 'frame': 'a.fits'}) == 0.7
    assert builder.slit_width_of({'frames': [{'filename': 'b.fits'}]}, {'slit': 1, 'frame': 'b.fits'}) is None
